"""Nested collection access, deep merge, comparison, filtering, and grouping."""

from __future__ import annotations

import copy
import itertools
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from rn_forge.commons.logging import AppLogger

_DOT_SPLITTER = re.compile(r"(?<!\\)\.")

_LOGGER = AppLogger.get_logger(__name__)

_NON_CONTAINER_SEGMENT_MSG = (
    "DictUtils.set | non_container_segment={} | type={} | key_path={}"
)


class _PathNotFound(Exception):
    """Internal control-flow signal: a `DictUtils.get` path segment could not be resolved."""


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Configuration and provenance returned by :meth:`DictUtils.merge_layers`."""

    config: dict[str, Any]
    provenance: dict[str, str]


# ---------------------------------------------------------------------------
# DictUtils — nested dict operations
# ---------------------------------------------------------------------------


class DictUtils:
    """Utilities for nested dict traversal, mutation, merging, and comparison.

    Dot-delimited key paths (e.g. ``"a.b.c"``) are supported; escape a literal
    dot with a backslash (``"a\\.b"``).
    """

    @staticmethod
    def get(
        data: Mapping[str, Any],
        key_path: str,
        *,
        default: Any = None,
    ) -> Any:
        """Retrieve a value from a nested dict using a dot-delimited key path.

        Supports both ``dict`` and ``list`` traversal; list indices are
        expressed as numeric path segments (e.g. ``"items.0.name"``).
        Escape a literal dot in a key with a backslash (``"a\\.b"``).

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, e.g. ``"a.b.0.c"``.
            default: Value returned when the path cannot be resolved. Defaults
                to ``None``.

        Returns:
            The resolved value, or *default* if any segment is missing,
            out of bounds, or *data*/*key_path* is empty.

        Example::

            data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
            DictUtils.get(data, "users.1.name")  # "Bob"
            DictUtils.get(data, "users.5.name", default="N/A")  # "N/A"
        """
        if not data or not key_path or not key_path.strip():
            _LOGGER.trace(
                "NO_TARGET_OR_KEY: {} == {}",
                len(data),
                len(key_path) if key_path else 0,
            )
            return default

        current: Any = data
        try:
            for token in _split_key_path(key_path):
                current = DictUtils._get_step(current, token, key_path)
        except _PathNotFound:
            return default
        return current

    @staticmethod
    def _get_step(current: Any, token: str, key_path: str) -> Any:
        """Resolve a single segment during `DictUtils.get` traversal.

        Raises:
            _PathNotFound: If *token* cannot be resolved against *current*.
        """
        if current is None:
            _LOGGER.trace("NO_KEY_VALUE: {} | {}", token, current)
            raise _PathNotFound

        if isinstance(current, Mapping):
            _dict = cast(Mapping[str, Any], current)
            if token not in _dict:
                _LOGGER.trace("MISSING_KEY_PART: {} | {}", token, _dict.keys())
                raise _PathNotFound
            return _dict[token]

        if isinstance(current, list):
            _list = cast(list[Any], current)
            if not token.isdigit():
                _LOGGER.warning(
                    "DictUtils.get | non_numeric_list_index={} | key_path={}",
                    token,
                    key_path,
                )
                raise _PathNotFound
            idx = int(token)
            if idx >= len(_list):
                _LOGGER.trace("INDEX_OUT_OF_BOUNDS: {} | {}", idx, _list)
                raise _PathNotFound
            return _list[idx]

        _LOGGER.trace("UNKNOWN_CONDITION: {} | {} | {}", token, type(current), current)
        raise _PathNotFound

    # -- typed reads: a value of the wrong shape reads as absent -----------

    @staticmethod
    def get_mapping(data: Mapping[str, Any], key_path: str) -> dict[str, object]:
        """Return the mapping at *key_path* as a string-keyed dict.

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, as for :meth:`get`.

        Returns:
            A shallow copy of the mapping with its keys converted to ``str``,
            or an empty dict if the path is missing or holds a non-mapping.

        Example::

            doc = {"repository": {"name": "kiln"}, "docs": "mkdocs"}
            DictUtils.get_mapping(doc, "repository")  # {"name": "kiln"}
            DictUtils.get_mapping(doc, "docs")        # {}
        """
        value = DictUtils.get(data, key_path)
        if not isinstance(value, Mapping):
            return {}
        items = cast(Mapping[object, object], value).items()
        return {str(key): item for key, item in items}

    @staticmethod
    def get_list(data: Mapping[str, Any], key_path: str) -> list[object]:
        """Return the list at *key_path*; a lone scalar reads as one element.

        Only a ``list`` is spread — a mapping or string is a single element.

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, as for :meth:`get`.

        Returns:
            A shallow copy of the list, ``[value]`` for any other non-``None``
            value, or an empty list if the path is missing or holds ``None``.

        Example::

            DictUtils.get_list({"cmds": "echo hi"}, "cmds")  # ["echo hi"]
            DictUtils.get_list({"cmds": None}, "cmds")       # []
        """
        value = DictUtils.get(data, key_path)
        if isinstance(value, list):
            return list(cast(list[object], value))
        return [] if value is None else [value]

    @staticmethod
    def get_strings(data: Mapping[str, Any], key_path: str) -> list[str]:
        """Return the string elements at *key_path*, ignoring anything else.

        Reads through :meth:`get_list`, so a lone string is a one-element list.

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, as for :meth:`get`.

        Returns:
            The ``str`` elements, in order; non-strings are dropped.

        Example::

            doc = {"dev": ["pytest", {"include-group": "lint"}]}
            DictUtils.get_strings(doc, "dev")  # ["pytest"]
        """
        return [
            item for item in DictUtils.get_list(data, key_path) if isinstance(item, str)
        ]

    @staticmethod
    def get_str(data: Mapping[str, Any], key_path: str, *, default: str = "") -> str:
        """Return the string at *key_path*, or *default* if it is not a ``str``.

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, as for :meth:`get`.
            default: Returned when the path is missing or holds a non-string.

        Returns:
            The string value, or *default*.
        """
        value = DictUtils.get(data, key_path)
        return value if isinstance(value, str) else default

    @staticmethod
    def get_bool(
        data: Mapping[str, Any], key_path: str, *, default: bool = False
    ) -> bool:
        """Return the boolean at *key_path*, or *default* if it is not a ``bool``.

        No truthiness coercion: ``"false"``, ``0`` and ``1`` read as absent.

        Args:
            data: The dictionary to search.
            key_path: Dot-delimited path, as for :meth:`get`.
            default: Returned when the path is missing or holds a non-boolean.

        Returns:
            The boolean value, or *default*.
        """
        value = DictUtils.get(data, key_path)
        return value if isinstance(value, bool) else default

    @staticmethod
    def set(
        data: dict[str, Any],
        key_path: str,
        value: Any,
    ) -> None:
        """Set a value in a nested dict using a dot-delimited key path.

        Intermediate dicts are created automatically when a segment is absent.
        List segments must reference existing indices — the list is never
        auto-extended.  Does nothing when *key_path* is empty or whitespace.

        Args:
            data: The dictionary to mutate in-place.
            key_path: Dot-delimited path to the target key, e.g.
                ``"database.host"``.
            value: The value to assign at the resolved path.

        Raises:
            KeyError: If a non-numeric index is used for a list segment.
            IndexError: If a list index is out of bounds.
            TypeError: When traversal encounters an existing value that is
                neither a ``dict`` nor a ``list``.

        Example::

            cfg: dict[str, Any] = {}
            DictUtils.set(cfg, "database.host", "localhost")
            assert cfg == {"database": {"host": "localhost"}}
        """
        if not key_path or not key_path.strip():
            _LOGGER.trace(
                "NO_KEY: {} | {}", len(data), len(key_path) if key_path else 0
            )
            return

        tokens = _split_key_path(key_path)
        last_token = tokens[-1]
        current = DictUtils._set_traverse(data, tokens, key_path)
        DictUtils._set_final_segment(current, last_token, value, key_path)

    @staticmethod
    def _set_traverse(data: dict[str, Any], tokens: list[str], key_path: str) -> Any:
        """Walk all but the last path segment, creating intermediate dicts as needed."""
        last_token = tokens[-1]
        current: Any = data
        for idx, token in enumerate(tokens[:-1]):
            _LOGGER.trace("KEY_PART: {} | {} | {}", idx, token, tokens[:-1])
            next_token = last_token if idx == len(tokens) - 2 else tokens[idx + 1]
            _LOGGER.trace("NEXT_VAL: {} | {}", idx, next_token)
            if isinstance(current, list):
                ls = cast(list[Any], current)
                list_index = DictUtils._resolve_list_index(ls, token, key_path)
                current = ls[list_index]
                continue
            current = DictUtils._set_dict_step(current, token, idx, tokens, key_path)
        return current

    @staticmethod
    def _set_dict_step(
        current: Any, token: str, idx: int, tokens: list[str], key_path: str
    ) -> Any:
        """Resolve (creating if absent) one dict-valued intermediate segment."""
        if not isinstance(current, dict):
            segment = ".".join(tokens[:idx]) or "<root>"
            DictUtils._raise_segment_type_error(
                key_path, segment, type(current).__name__, "resolved to"
            )

        d = cast(dict[str, Any], current)
        if token not in d:
            next_value: Any = {}
            d[token] = next_value
            return next_value

        next_value = d[token]
        if not isinstance(next_value, (dict, list)):
            segment = ".".join(tokens[: idx + 1])
            DictUtils._raise_segment_type_error(
                key_path, segment, type(next_value).__name__, "holds"
            )
        return cast(Any, next_value)

    @staticmethod
    def _set_final_segment(
        current: Any, last_token: str, value: Any, key_path: str
    ) -> None:
        """Assign *value* onto the resolved container at the final path segment."""
        if isinstance(current, list):
            ls = cast(list[Any], current)
            idx = DictUtils._resolve_list_index(ls, last_token, key_path)
            ls[idx] = value
            return

        if not isinstance(current, dict):
            segment = "<root>"
            DictUtils._raise_segment_type_error(
                key_path, segment, type(current).__name__, "resolved to"
            )
        d = cast(dict[str, Any], current)
        d[last_token] = value

    @staticmethod
    def _resolve_list_index(items: list[Any], token: str, key_path: str) -> int:
        """Validate *token* as an in-bounds numeric list index for `DictUtils.set`."""
        if not token.isdigit():
            _LOGGER.warning(
                "DictUtils.set | non_numeric_list_index={} | key_path={}",
                token,
                key_path,
            )
            raise KeyError(f"Non-numeric index '{token}' for list in path '{key_path}'")
        index = int(token)
        if index >= len(items):
            _LOGGER.warning(
                "DictUtils.set | list_index_out_of_bounds={} | length={} | key_path={}",
                index,
                len(items),
                key_path,
            )
            raise IndexError(
                f"Index {index} out of bounds (len={len(items)}) in path '{key_path}'"
            )
        return index

    @staticmethod
    def _raise_segment_type_error(
        key_path: str, segment: str, type_name: str, verb: str
    ) -> NoReturn:
        """Log and raise the `TypeError` for a non-container segment in `DictUtils.set`."""
        _LOGGER.warning(_NON_CONTAINER_SEGMENT_MSG, segment, type_name, key_path)
        raise TypeError(
            f"Cannot traverse path '{key_path}': segment '{segment}' "
            f"{verb} non-container type '{type_name}'"
        )

    @staticmethod
    def merge(target: dict[str, Any], *overrides: dict[str, Any]) -> dict[str, Any]:
        """Deep-merge one or more *overrides* dicts into *target*, mutating *target*.

        Merging rules:

        - ``dict`` values are merged recursively.
        - Non-``dict`` values in *overrides* replace the corresponding value
          in *target*.
        - Override values are deep-copied to prevent shared references between
          *target* and *overrides*.
        - Empty or ``None`` override dicts are silently skipped.

        Args:
            target: The dictionary to merge into (mutated in-place).
            *overrides: One or more dicts whose values are merged into *target*
                in order.

        Returns:
            *target* after merging, enabling chained calls.

        Example::

            base = {"a": {"x": 1}, "b": 2}
            DictUtils.merge(base, {"a": {"y": 3}, "b": 99})
            # {"a": {"x": 1, "y": 3}, "b": 99}
        """
        if not overrides:
            _LOGGER.debug("No overrides provided")
            return target

        for override in overrides:
            if not override:
                continue
            DictUtils._merge_override(target, override)
        return target

    @staticmethod
    def _merge_override(target: dict[str, Any], override: dict[str, Any]) -> None:
        """Merge a single *override* dict's keys into *target*."""
        _LOGGER.debug(
            "DictUtils.merge | override_keys={} | target_size={}",
            sorted(override),
            len(target),
        )
        for key, value in override.items():
            DictUtils._merge_key(target, key, value)

    @staticmethod
    def _merge_key(target: dict[str, Any], key: str, value: Any) -> None:
        """Merge a single *key*/*value* pair from an override into *target*."""
        new_value = copy.deepcopy(value)
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(new_value, dict):
            DictUtils.merge(
                cast(dict[str, Any], existing), cast(dict[str, Any], new_value)
            )
            return
        if key in target and existing != new_value:
            _LOGGER.trace("OVERRIDE: {}", [key])
        target[key] = new_value

    #: Conventional layer names assigned to unnamed :meth:`merge_layers` layers,
    #: in order. Layers beyond this get ``"layer-N"`` (1-indexed).
    _CONVENTIONAL_LAYER_NAMES: tuple[str, ...] = (
        "defaults",
        "global",
        "local",
        "overrides",
    )

    @staticmethod
    def merge_layers(
        *layers: Mapping[str, Any] | tuple[str, Mapping[str, Any]],
        layer_names: Sequence[str] | None = None,
        append_paths: Collection[str] = (),
    ) -> MergeResult:
        """Deep-merge *layers* in increasing precedence order, tracking provenance.

        Unlike :meth:`merge`, every dotted key path in the result is tracked
        back to the name of the highest-precedence layer that supplied it —
        this is what drives a ``diff``/``doctor``-style command that explains
        *where* each config value came from. This does not replace
        :meth:`merge`, whose signature and semantics are unchanged and remain
        load-bearing elsewhere; this is additive.

        Args:
            *layers: Each layer is either a plain mapping or an explicit
                ``(name, mapping)`` pair. Unnamed layers are assigned
                conventional names in order: ``"defaults"``, ``"global"``,
                ``"local"``, ``"overrides"``, then ``"layer-N"``.
            layer_names: Explicit names for the unnamed layers, by position.
                Overridden by an explicit ``(name, mapping)`` tuple at that
                position.
            append_paths: Dotted paths (``DictUtils.get``-style, e.g.
                ``"servers.hosts"``) whose list values concatenate across
                layers instead of the default replace-wholesale behaviour.

        Returns:
            A :class:`MergeResult` with the merged ``config`` and a
            ``provenance`` map of dotted path -> layer name. A subtree
            introduced wholesale by one layer gets a provenance entry on
            every leaf, not just the subtree root.

        Example::

            result = DictUtils.merge_layers(
                {"a": 1}, ("overrides", {"a": 2}),
            )
            result.config       # {"a": 2}
            result.provenance   # {"a": "overrides"}
        """
        named: list[tuple[str, Mapping[str, Any]]] = []
        for index, layer in enumerate(layers):
            if isinstance(layer, tuple):
                named.append(layer)
                continue
            if layer_names and index < len(layer_names):
                name = layer_names[index]
            elif index < len(DictUtils._CONVENTIONAL_LAYER_NAMES):
                name = DictUtils._CONVENTIONAL_LAYER_NAMES[index]
            else:
                name = f"layer-{index + 1}"
            named.append((name, layer))

        merged: dict[str, Any] = {}
        provenance: dict[str, str] = {}
        append_path_set = set(append_paths)
        for name, layer in named:
            _deep_merge_layer(merged, layer, name, provenance, append_path_set)
        return MergeResult(config=merged, provenance=provenance)

    @staticmethod
    def flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
        """Flatten nested mappings into a single level of dotted-path keys.

        The inverse of the dotted-path traversal :meth:`get`/:meth:`set`
        already perform — ``{"a": {"b": 1}}`` becomes ``{"a.b": 1}``. A dict
        key containing a literal ``.`` is escaped as ``\\.`` in the flattened
        key, matching :meth:`get`/:meth:`set`'s own escaping convention.

        Args:
            value: The (possibly nested) mapping to flatten.
            prefix: Internal recursion accumulator — leave at the default.

        Returns:
            A single-level dict whose keys are dotted paths.

        Example::

            DictUtils.flatten({"a": {"b": 1, "c": 2}, "d": 3})
            # {"a.b": 1, "a.c": 2, "d": 3}
        """
        result: dict[str, Any] = {}
        for key, item in value.items():
            escaped_key = str(key).replace(".", "\\.")
            path = f"{prefix}.{escaped_key}" if prefix else escaped_key
            if isinstance(item, Mapping):
                result.update(DictUtils.flatten(cast(Mapping[str, Any], item), path))
            else:
                result[path] = item
        return result

    @staticmethod
    def compare(
        dict_a: Mapping[str, Any],
        dict_b: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return a structural diff between two dicts.

        The result dict may contain the following top-level keys:

        - ``"only_in_a"``: mapping of keys present in *dict_a* but not
          *dict_b*.
        - ``"only_in_b"``: mapping of keys present in *dict_b* but not
          *dict_a*.
        - ``"conflicts"``: mapping of keys present in both with differing
          values.  For nested dicts the value is a recursive diff result;
          for leaf values it is ``[value_a, value_b]``.

        Args:
            dict_a: The first dictionary.
            dict_b: The second dictionary.

        Returns:
            A diff dict, or an empty dict when the two inputs are structurally
            equal.

        Example::

            DictUtils.compare({"a": 1, "b": 2}, {"b": 3, "c": 4})
            # {
            #   "only_in_a": {"a": 1},
            #   "only_in_b": {"c": 4},
            #   "conflicts": {"b": [2, 3]},
            # }
        """
        result: dict[str, Any] = {}

        if not dict_a and not dict_b:
            return result
        if not dict_b:
            return {"only_in_a": copy.deepcopy(dict_a)}
        if not dict_a:
            return {"only_in_b": copy.deepcopy(dict_b)}

        for key, value_a in dict_a.items():
            DictUtils._compare_a_key(result, key, value_a, dict_b)

        for key, value_b in dict_b.items():
            if key not in dict_a:
                result.setdefault("only_in_b", {})[key] = copy.deepcopy(value_b)

        _LOGGER.trace(
            "DictUtils.compare | only_in_a={} | only_in_b={} | conflicts={}",
            len(cast(dict[str, Any], result.get("only_in_a", {}))),
            len(cast(dict[str, Any], result.get("only_in_b", {}))),
            len(cast(dict[str, Any], result.get("conflicts", {}))),
        )
        return result

    @staticmethod
    def _compare_a_key(
        result: dict[str, Any],
        key: str,
        value_a: Any,
        dict_b: Mapping[str, Any],
    ) -> None:
        """Compare one `dict_a` key/value against `dict_b`, recording into *result*."""
        if key not in dict_b:
            result.setdefault("only_in_a", {})[key] = copy.deepcopy(value_a)
            return
        value_b = dict_b[key]
        if isinstance(value_a, Mapping) and isinstance(value_b, Mapping):
            nested = DictUtils.compare(
                cast(Mapping[str, Any], value_a),
                cast(Mapping[str, Any], value_b),
            )
            if nested:
                result.setdefault("conflicts", {})[key] = nested
        elif value_a != value_b:
            result.setdefault("conflicts", {})[key] = [
                copy.deepcopy(cast(Any, value_a)),
                copy.deepcopy(value_b),
            ]


# ---------------------------------------------------------------------------
# ListUtils — list operations
# ---------------------------------------------------------------------------


class ListUtils:
    """Utilities for list access, sorting, filtering, and grouping."""

    @staticmethod
    def get(items: list[Any], index: int = 0, *, default: Any = None) -> Any:
        """Return the item at *index*, or *default* when missing."""
        if not items:
            _LOGGER.trace("ListUtils.get: empty list | index={}", index)
            return default
        try:
            value = items[index]
            _LOGGER.trace("ListUtils.get: found | index={} | value={}", index, value)
            return value
        except IndexError:
            _LOGGER.trace(
                "ListUtils.get: index out of bounds | index={} | length={}",
                index,
                len(items),
            )
            return default

    @staticmethod
    def sort(
        items: list[Any],
        key: Callable[[Any], Any] | None = None,
        reverse: bool = False,
    ) -> list[Any]:
        """Sort *items* in-place and return it."""
        _LOGGER.debug(
            "ListUtils.sort: sorting list | length={} | reverse={}",
            len(items),
            reverse,
        )
        items.sort(key=key, reverse=reverse)
        _LOGGER.trace("ListUtils.sort: sorted list | items={}", items)
        return items

    @staticmethod
    def filter(
        items: list[Any],
        predicate: Callable[[Any], bool] | Any,
    ) -> list[Any]:
        """Return items matching *predicate* or equal to *predicate*."""
        if callable(predicate):
            result = [item for item in items if predicate(item)]
            _LOGGER.debug(
                "ListUtils.filter: predicate applied | input_length={} | output_length={}",
                len(items),
                len(result),
            )
            _LOGGER.trace("ListUtils.filter: result={}", result)
            return result

        result = [item for item in items if item == predicate]
        _LOGGER.debug(
            "ListUtils.filter: value matched | value={} | input_length={} | output_length={}",
            predicate,
            len(items),
            len(result),
        )
        _LOGGER.trace("ListUtils.filter: result={}", result)
        return result

    @staticmethod
    def group_by(
        items: list[Any],
        key_fn: Callable[[Any], str],
        value_fn: Callable[[Any], Any] | None = None,
        group_fn: Callable[[list[Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Group *items* by *key_fn* without mutating the input list."""
        if not items:
            _LOGGER.trace("ListUtils.group_by: empty list")
            return {}

        _LOGGER.debug("ListUtils.group_by: grouping list | length={}", len(items))
        sorted_items = sorted(items, key=key_fn)
        grouped: dict[str, Any] = {
            key: [value_fn(item) if value_fn else item for item in group]
            for key, group in itertools.groupby(sorted_items, key_fn)
        }
        _LOGGER.trace("ListUtils.group_by: grouped={}", grouped)

        if group_fn:
            result = {key: group_fn(value) for key, value in grouped.items()}
            _LOGGER.debug(
                "ListUtils.group_by: group function applied | groups={}",
                list(result.keys()),
            )
            _LOGGER.trace("ListUtils.group_by: result={}", result)
            return result

        _LOGGER.debug("ListUtils.group_by: complete | groups={}", list(grouped.keys()))
        return grouped


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _split_key_path(key_path: str) -> list[str]:
    """Split a dot-delimited key path, respecting backslash-escaped dots."""
    return [part.replace("\\.", ".") for part in _DOT_SPLITTER.split(key_path)]


def _deep_merge_layer(
    target: dict[str, Any],
    incoming: Mapping[str, Any],
    layer: str,
    provenance: dict[str, str],
    append_paths: set[str],
    prefix: str = "",
) -> None:
    """Merge one named *layer* into *target*, recording provenance for :meth:`DictUtils.merge_layers`."""
    for raw_key, value in incoming.items():
        key = str(raw_key)
        escaped_key = key.replace(".", "\\.")
        path = f"{prefix}.{escaped_key}" if prefix else escaped_key
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge_layer(
                cast(dict[str, Any], target[key]),
                cast(Mapping[str, Any], value),
                layer,
                provenance,
                append_paths,
                path,
            )
            provenance[path] = layer
        elif isinstance(value, Mapping):
            target[key] = {}
            _deep_merge_layer(
                cast(dict[str, Any], target[key]),
                cast(Mapping[str, Any], value),
                layer,
                provenance,
                append_paths,
                path,
            )
            provenance[path] = layer
        elif (
            path in append_paths
            and isinstance(value, list)
            and isinstance(target.get(key), list)
        ):
            current: list[Any] = cast(list[Any], target[key])
            incoming_list: list[Any] = cast(list[Any], value)
            target[key] = copy.deepcopy(current) + copy.deepcopy(incoming_list)
            provenance[path] = layer
        else:
            if isinstance(target.get(key), Mapping):
                for descendant in list(provenance):
                    if descendant.startswith(f"{path}."):
                        del provenance[descendant]
            target[key] = copy.deepcopy(cast(Any, value))
            provenance[path] = layer


__all__ = [
    "DictUtils",
    "ListUtils",
    "MergeResult",
]
