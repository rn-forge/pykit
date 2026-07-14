"""Collection utilities for nested dict/list access, deep merge, and serialisation I/O.

Provides:
    DictUtils: Dot-path get/set, deep merge, and structural comparison
        for nested dictionaries.
    ListUtils: List access, sorting, filtering, and grouping helpers.
    JsonUtils: JSON load/serialize/file I/O with dataclass-aware
        serialisation and sensible defaults.
    YamlUtils: YAML load/serialize/file I/O with multi-document support.

All methods are pure functions with no import-time side effects.

Typical usage::

    from rn_forge.commons.collections import DictUtils, JsonUtils

    data = {"a": {"b": {"c": 42}}}
    value = DictUtils.get(data, "a.b.c")  # 42

    json_str = JsonUtils.serialize({"key": "value"})
"""

from __future__ import annotations

import copy
import itertools
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from rn_forge.commons.logging import AppLogger

_DOT_SPLITTER = re.compile(r"(?<!\\)\.")

_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# DictUtils — nested dict operations
# ---------------------------------------------------------------------------


class DictUtils:
    """Utilities for nested dict traversal, mutation, merging, and comparison.

    All methods are static.  Dot-delimited key paths (e.g. ``"a.b.c"``) are
    supported; escape a literal dot with a backslash (``"a\\.b"``).
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
        for token in _split_key_path(key_path):
            if current is None:
                _LOGGER.trace("NO_KEY_VALUE: {} | {}", token, current)
                return default

            if isinstance(current, Mapping):
                _dict = cast(Mapping[str, Any], current)
                if token not in _dict:
                    _LOGGER.trace("MISSING_KEY_PART: {} | {}", token, _dict.keys())
                    return default
                current = _dict[token]
            elif isinstance(current, list):
                _list = cast(list[Any], current)
                if not token.isdigit():
                    _LOGGER.warning(
                        "DictUtils.get | non_numeric_list_index={} | key_path={}",
                        token,
                        key_path,
                    )
                    return default
                idx = int(token)
                if idx >= len(_list):
                    _LOGGER.trace("INDEX_OUT_OF_BOUNDS: {} | {}", idx, _list)
                    return default
                current = _list[idx]
            else:
                _LOGGER.trace(
                    "UNKNOWN_CONDITION: {} | {} | {}", token, type(current), current
                )
                return default

        return current

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
        current: Any = data

        for idx, token in enumerate(tokens[:-1]):
            _LOGGER.trace("KEY_PART: {} | {} | {}", idx, token, tokens[:-1])
            next_token = last_token if idx == len(tokens) - 2 else tokens[idx + 1]
            _LOGGER.trace("NEXT_VAL: {} | {}", idx, next_token)
            if isinstance(current, list):
                ls = cast(list[Any], current)
                if not token.isdigit():
                    _LOGGER.warning(
                        "DictUtils.set | non_numeric_list_index={} | key_path={}",
                        token,
                        key_path,
                    )
                    raise KeyError(
                        f"Non-numeric index '{token}' for list in path '{key_path}'"
                    )
                index = int(token)
                if index >= len(ls):
                    _LOGGER.warning(
                        "DictUtils.set | list_index_out_of_bounds={} | length={} | key_path={}",
                        index,
                        len(ls),
                        key_path,
                    )
                    raise IndexError(
                        f"Index {index} out of bounds (len={len(ls)}) in path '{key_path}'"
                    )
                current = ls[index]
                continue

            if not isinstance(current, dict):
                segment = ".".join(tokens[:idx]) or "<root>"
                _LOGGER.warning(
                    "DictUtils.set | non_container_segment={} | type={} | key_path={}",
                    segment,
                    type(current).__name__,
                    key_path,
                )
                raise TypeError(
                    "Cannot traverse path '{path}': segment '{segment}' "
                    "resolved to non-container type '{type_name}'".format(
                        path=key_path,
                        segment=segment,
                        type_name=type(current).__name__,
                    )
                )

            d = cast(dict[str, Any], current)
            if token not in d:
                next_value: Any = {}
                d[token] = next_value
            else:
                next_value = d[token]
                if not isinstance(next_value, (dict, list)):
                    segment = ".".join(tokens[: idx + 1])
                    _LOGGER.warning(
                        "DictUtils.set | non_container_segment={} | type={} | key_path={}",
                        segment,
                        type(next_value).__name__,
                        key_path,
                    )
                    raise TypeError(
                        "Cannot traverse path '{path}': segment '{segment}' "
                        "holds non-container type '{type_name}'".format(
                            path=key_path,
                            segment=segment,
                            type_name=type(next_value).__name__,
                        )
                    )
            current = cast(Any, next_value)

        if isinstance(current, list):
            ls = cast(list[Any], current)
            if not last_token.isdigit():
                _LOGGER.warning(
                    "DictUtils.set | non_numeric_list_index={} | key_path={}",
                    last_token,
                    key_path,
                )
                raise KeyError(
                    f"Non-numeric index '{last_token}' for list in path '{key_path}'"
                )
            idx = int(last_token)
            if idx >= len(ls):
                _LOGGER.warning(
                    "DictUtils.set | list_index_out_of_bounds={} | length={} | key_path={}",
                    idx,
                    len(ls),
                    key_path,
                )
                raise IndexError(
                    f"Index {idx} out of bounds (len={len(ls)}) in path '{key_path}'"
                )
            ls[idx] = value
            return

        if not isinstance(current, dict):
            segment = ".".join(tokens[:-1]) or "<root>"
            _LOGGER.warning(
                "DictUtils.set | non_container_segment={} | type={} | key_path={}",
                segment,
                type(current).__name__,
                key_path,
            )
            raise TypeError(
                "Cannot traverse path '{path}': segment '{segment}' "
                "resolved to non-container type '{type_name}'".format(
                    path=key_path,
                    segment=segment,
                    type_name=type(current).__name__,
                )
            )
        d = cast(dict[str, Any], current)
        d[last_token] = value

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
            _LOGGER.debug(
                "DictUtils.merge | override_keys={} | target_size={}",
                sorted(override),
                len(target),
            )
            for key, value in override.items():
                new_value = copy.deepcopy(value)
                existing = target.get(key)
                if isinstance(existing, dict) and isinstance(new_value, dict):
                    DictUtils.merge(
                        cast(dict[str, Any], existing), cast(dict[str, Any], new_value)
                    )
                else:
                    if key in target and existing != new_value:
                        _LOGGER.trace("OVERRIDE: {}", [key])
                    target[key] = new_value
        return target

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
            if key not in dict_b:
                result.setdefault("only_in_a", {})[key] = copy.deepcopy(value_a)
                continue
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
# JsonUtils — JSON load / serialize / file I/O
# ---------------------------------------------------------------------------


class JsonUtils:
    """JSON helpers with dataclass-aware serialisation and file I/O."""

    @staticmethod
    def load(text: str, *, root_key: str | None = None) -> Any:
        """Parse a JSON string and return the resulting Python object.

        Args:
            text: Raw JSON text.
            root_key: When provided, return only the value at this top-level
                key from the parsed object.

        Returns:
            The parsed Python object, or the value at *root_key* if given.

        Raises:
            json.JSONDecodeError: If *text* is not valid JSON.
            KeyError: If *root_key* is provided but absent from the parsed
                object.
        """
        _LOGGER.trace(
            "JsonUtils.load | root_key={} | text_length={}",
            root_key,
            len(text),
        )
        try:
            obj = json.loads(text)
        except Exception:
            _LOGGER.exception(
                "JsonUtils.load failed | root_key={} | text_length={}",
                root_key,
                len(text),
            )
            raise
        if root_key is not None:
            _LOGGER.trace("JsonUtils.load selecting root key | root_key={}", root_key)
            return obj[root_key]
        return obj

    @staticmethod
    def serialize(obj: Any, **kwargs: Any) -> str:
        """Serialise *obj* to a JSON string.

        Dataclasses are automatically converted via ``dataclasses.asdict()``.
        Other non-serialisable objects fall back to ``repr()``.

        Args:
            obj: The Python object to serialise.
            **kwargs: Forwarded to :func:`json.dumps` (e.g. ``indent``,
                ``sort_keys``).

        Returns:
            A JSON string representation of *obj*.
        """
        kwargs.setdefault("default", _json_default)
        _LOGGER.trace(
            "JsonUtils.serialize | type={} | kwargs={}",
            type(obj).__name__,
            sorted(kwargs),
        )
        try:
            return json.dumps(obj, **kwargs)
        except Exception:
            _LOGGER.exception(
                "JsonUtils.serialize failed | type={}",
                type(obj).__name__,
            )
            raise

    @staticmethod
    def read_file(path: str | Path, *, encoding: str | None = None) -> Any:
        """Read and parse a JSON file.

        Args:
            path: Path to the ``.json`` file.
            encoding: Text encoding passed to :meth:`~pathlib.Path.read_text`.
                Defaults to the platform default when ``None``.

        Returns:
            The parsed Python object.

        Raises:
            FileNotFoundError: If *path* does not exist.
            json.JSONDecodeError: If the file content is not valid JSON.
        """
        _LOGGER.verbose("JsonUtils.read_file | path={} | encoding={}", path, encoding)
        try:
            return JsonUtils.load(Path(path).read_text(encoding=encoding))
        except Exception:
            _LOGGER.exception("JsonUtils.read_file failed | path={}", path)
            raise

    @staticmethod
    def write_file(
        obj: Any,
        path: str | Path,
        *,
        indent: str | int = "\t",
        encoding: str | None = None,
        **kwargs: Any,
    ) -> Path:
        """Serialise *obj* to JSON and write to *path*, creating parents as needed.

        Args:
            obj: The Python object to serialise.
            path: Destination file path.
            indent: Indentation for pretty-printing. Defaults to a tab
                character (``"\\t"``).
            encoding: Text encoding for the output file. Defaults to the
                platform default when ``None``.
            **kwargs: Additional keyword arguments forwarded to
                :meth:`JsonUtils.serialize`.

        Returns:
            The resolved :class:`~pathlib.Path` that was written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.verbose(
            "JsonUtils.write_file | path={} | indent={} | type={}",
            p,
            indent,
            type(obj).__name__,
        )
        try:
            p.write_text(
                JsonUtils.serialize(obj, indent=indent, **kwargs),
                encoding=encoding,
            )
        except Exception:
            _LOGGER.exception("JsonUtils.write_file failed | path={}", p)
            raise
        return p


# ---------------------------------------------------------------------------
# YamlUtils — YAML load / serialize / file I/O (requires pyyaml)
# ---------------------------------------------------------------------------


class YamlUtils:
    """YAML helpers with multi-document support and file I/O."""

    @staticmethod
    def load(text: str, *, root_key: str | None = None) -> Any:
        """Parse a YAML string and return the resulting Python object.

        Args:
            text: Raw YAML text.
            root_key: When provided, return only the value at this top-level
                key from the parsed object.

        Returns:
            The parsed Python object, or the value at *root_key* if given.

        Raises:
            KeyError: If *root_key* is provided but absent from the parsed
                object.
        """
        _LOGGER.trace(
            "YamlUtils.load | root_key={} | text_length={}",
            root_key,
            len(text),
        )
        try:
            obj = yaml.safe_load(text)
        except Exception:
            _LOGGER.exception(
                "YamlUtils.load failed | root_key={} | text_length={}",
                root_key,
                len(text),
            )
            raise
        if root_key is not None:
            _LOGGER.trace("YamlUtils.load selecting root key | root_key={}", root_key)
            return obj[root_key]
        return obj

    @staticmethod
    def load_all(text: str) -> list[Any]:
        """Parse a multi-document YAML string.

        Skips documents that parse to ``None`` (empty ``---`` separators).

        Args:
            text: Raw multi-document YAML text.

        Returns:
            A list of parsed Python objects, one per non-empty document.
        """
        _LOGGER.trace("YamlUtils.load_all | text_length={}", len(text))
        try:
            docs = [doc for doc in yaml.safe_load_all(text) if doc is not None]
        except Exception:
            _LOGGER.exception("YamlUtils.load_all failed | text_length={}", len(text))
            raise
        _LOGGER.trace("YamlUtils.load_all complete | documents={}", len(docs))
        return docs

    @staticmethod
    def serialize(obj: Any, *, sort_keys: bool = False, **kwargs: Any) -> str:
        """Serialise *obj* to a YAML string.

        Args:
            obj: The Python object to serialise.
            sort_keys: When ``True``, sort mapping keys alphabetically.
                Defaults to ``False``.
            **kwargs: Additional keyword arguments forwarded to
                :func:`yaml.dump`.

        Returns:
            A YAML string representation of *obj*.
        """
        _LOGGER.trace(
            "YamlUtils.serialize | type={} | sort_keys={} | kwargs={}",
            type(obj).__name__,
            sort_keys,
            sorted(kwargs),
        )
        try:
            return cast(str, yaml.dump(obj, sort_keys=sort_keys, **kwargs))
        except Exception:
            _LOGGER.exception(
                "YamlUtils.serialize failed | type={}",
                type(obj).__name__,
            )
            raise

    @staticmethod
    def serialize_all(*objs: Any, sort_keys: bool = False, **kwargs: Any) -> str:
        """Serialise multiple objects as a multi-document YAML string.

        Args:
            *objs: Python objects to serialise as separate YAML documents.
            sort_keys: When ``True``, sort mapping keys alphabetically.
                Defaults to ``False``.
            **kwargs: Additional keyword arguments forwarded to
                :func:`yaml.dump_all`.

        Returns:
            A YAML string with ``---`` document separators between objects.
        """
        _LOGGER.trace(
            "YamlUtils.serialize_all | documents={} | sort_keys={} | kwargs={}",
            len(objs),
            sort_keys,
            sorted(kwargs),
        )
        try:
            return cast(str, yaml.dump_all(objs, sort_keys=sort_keys, **kwargs))
        except Exception:
            _LOGGER.exception(
                "YamlUtils.serialize_all failed | documents={}",
                len(objs),
            )
            raise

    @staticmethod
    def read_file(
        path: str | Path,
        *,
        root_key: str | None = None,
        encoding: str | None = None,
    ) -> Any:
        """Read and parse a YAML file.

        Args:
            path: Path to the ``.yaml`` / ``.yml`` file.
            root_key: When provided, return only the value at this top-level
                key from the parsed document.
            encoding: Text encoding passed to :meth:`~pathlib.Path.read_text`.
                Defaults to the platform default when ``None``.

        Returns:
            The parsed Python object, or the value at *root_key* if given.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        _LOGGER.verbose(
            "YamlUtils.read_file | path={} | root_key={} | encoding={}",
            path,
            root_key,
            encoding,
        )
        try:
            return YamlUtils.load(
                Path(path).read_text(encoding=encoding), root_key=root_key
            )
        except Exception:
            _LOGGER.exception("YamlUtils.read_file failed | path={}", path)
            raise

    @staticmethod
    def read_file_all(path: str | Path, *, encoding: str | None = None) -> list[Any]:
        """Read and parse a multi-document YAML file.

        Args:
            path: Path to the ``.yaml`` / ``.yml`` file.
            encoding: Text encoding passed to :meth:`~pathlib.Path.read_text`.
                Defaults to the platform default when ``None``.

        Returns:
            A list of parsed Python objects, one per non-empty YAML document
            in the file.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        _LOGGER.verbose(
            "YamlUtils.read_file_all | path={} | encoding={}", path, encoding
        )
        try:
            return YamlUtils.load_all(Path(path).read_text(encoding=encoding))
        except Exception:
            _LOGGER.exception("YamlUtils.read_file_all failed | path={}", path)
            raise

    @staticmethod
    def write_file(
        obj: Any,
        path: str | Path,
        *,
        encoding: str | None = None,
        **kwargs: Any,
    ) -> Path:
        """Serialise *obj* to YAML and write to *path*, creating parents as needed.

        Args:
            obj: The Python object to serialise.
            path: Destination file path.
            encoding: Text encoding for the output file. Defaults to the
                platform default when ``None``.
            **kwargs: Additional keyword arguments forwarded to
                :meth:`YamlUtils.serialize`.

        Returns:
            The resolved :class:`~pathlib.Path` that was written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.verbose(
            "YamlUtils.write_file | path={} | type={}",
            p,
            type(obj).__name__,
        )
        try:
            p.write_text(YamlUtils.serialize(obj, **kwargs), encoding=encoding)
        except Exception:
            _LOGGER.exception("YamlUtils.write_file failed | path={}", p)
            raise
        return p


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _split_key_path(key_path: str) -> list[str]:
    """Split a dot-delimited key path, respecting backslash-escaped dots."""
    return [part.replace("\\.", ".") for part in _DOT_SPLITTER.split(key_path)]


def _json_default(obj: object) -> Any:
    """Default JSON serialiser: dataclass → dict, otherwise repr()."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return repr(obj)


__all__ = [
    "DictUtils",
    "JsonUtils",
    "ListUtils",
    "YamlUtils",
]
