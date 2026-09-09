"""Configuration loader with reference resolution.

Loads configuration from JSON or YAML files (single file or directory),
deep-merges multiple files, and resolves internal references:

- ``${path}`` — value interpolation (replaces with the resolved value)
- ``@{path}`` — dict reference (resolves to the dict at *path*)
- ``#{path}`` — list reference (resolves to the list at *path*)
- ``__extends__`` key — inherits and merges from another dict path

Reference paths use the same dot-delimited notation as
:meth:`~rn_forge.commons.collections.DictUtils.get`.

Provides:
    Config: Immutable-ish configuration object loaded from one or more
        JSON/YAML files with automatic reference resolution.

Typical usage::

    from rn_forge.commons.config import Config

    cfg = Config("settings", "base.yaml")
    db_host = cfg.get("database.host", default="localhost")
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, cast

from rn_forge.commons.collections import DictUtils
from rn_forge.commons.documents import JsonUtils, YamlUtils
from rn_forge.commons.logging import AppLogger

_SENTINEL = object()

_REF_DICT_PATTERN = re.compile(r"^@\{(.+)}$")
_REF_LIST_PATTERN = re.compile(r"^#\{(.+)}$")
_REF_VALUE_PATTERN = re.compile(r"\$\{([^{}]+)}")

_MAX_RESOLVE_DEPTH = 64

_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class Config:
    """Immutable-ish configuration object with reference resolution.

    Loads one or more JSON/YAML files, deep-merges them in sorted order, and
    optionally resolves internal ``${}``, ``@{}``, ``#{}`` references and
    ``__extends__`` inheritance.

    Supports dict-like read access via ``cfg["key"]``, ``"key" in cfg``,
    ``iter(cfg)``, and ``len(cfg)``.

    Example::

        from rn_forge.commons.config import Config

        cfg = Config("config/")
        host = cfg.get("database.host", default="localhost")
        cfg.set("database.port", 5432)
        raw = cfg.as_dict()

    Reference forms::

        service_url: "https://${service.host}:${service.port}"
        database: "@{services.primary_db}"
        all_hosts:
          - "#{services.hosts}"
          - "localhost"
        production:
          __extends__: "@{profiles.base}"
          debug: false
    """

    def __init__(
        self,
        *paths: str | Path,
        config_type: Literal["json", "yaml"] = "yaml",
        resolve: bool = True,
    ) -> None:
        """Load and optionally resolve a configuration from file(s).

        Args:
            *paths: Path segments joined via :class:`~pathlib.Path`.  If the
                result is a file it is loaded directly; if a directory, all
                files matching ``*.{config_type}`` (recursively, sorted) are
                loaded and deep-merged.
            config_type: ``"yaml"`` (default) or ``"json"`` — determines
                the file extension filter and parser.
            resolve: When ``True`` (default), call
                :meth:`resolve_references` immediately after loading.

        Raises:
            FileNotFoundError: If the resolved path does not exist.
        """
        config_path = Path(*paths)
        if not config_path.exists():
            _LOGGER.warning("Config.__init__ | path={} | missing=true", config_path)
            raise FileNotFoundError(f"Config path not found: {config_path}")

        config_files = (
            [config_path]
            if config_path.is_file()
            else sorted(config_path.rglob(f"*.{config_type}"))
        )
        _LOGGER.verbose("config_files: {}", config_files)

        reader = JsonUtils.read_file if config_type == "json" else YamlUtils.read_file
        configs = [reader(f) for f in config_files]
        _LOGGER.trace("config_list: {}", configs)

        self._data: dict[str, Any] = {}
        DictUtils.merge(self._data, *configs)

        if resolve:
            self.resolve_references()
        _LOGGER.success("Config Loaded: {}", config_path)

    # -- public API --------------------------------------------------------

    def get(self, key_path: str, *, default: Any = None) -> Any:
        """Retrieve a value using a dot-delimited key path.

        Delegates to :meth:`~rn_forge.commons.collections.DictUtils.get`.

        Args:
            key_path: Dot-delimited path, e.g. ``"database.host"``.
            default: Value returned when the path cannot be resolved.
                Defaults to ``None``.

        Returns:
            The resolved value, or *default* if the path is absent.
        """
        return DictUtils.get(self._data, key_path, default=default)

    def set(self, key_path: str, value: Any) -> None:
        """Set a value using a dot-delimited key path.

        Delegates to :meth:`~rn_forge.commons.collections.DictUtils.set`.
        Intermediate dicts are created automatically.

        Args:
            key_path: Dot-delimited path to the target key.
            value: The value to assign.

        Raises:
            KeyError: If a non-numeric index is used on a list segment.
            IndexError: If a list index is out of bounds.
            TypeError: If traversal encounters a non-container at an
                intermediate path segment.
        """
        DictUtils.set(self._data, key_path, value)

    def as_dict(self) -> dict[str, Any]:
        """Return a deep copy of the configuration data as a plain dict.

        Returns:
            A deep copy of the internal ``dict[str, Any]``. Mutating the
            returned value does not affect this :class:`Config` instance.
        """
        return copy.deepcopy(self._data)

    def resolve_references(self) -> None:
        """Resolve all ``${}``, ``@{}``, ``#{}`` references and ``__extends__``
        inheritance in the loaded configuration.

        Called automatically when ``resolve=True`` (the default).  Safe to call
        again after programmatic mutations.

        Example::

            cfg = Config("settings.yaml", resolve=False)
            cfg.set("service.host", "localhost")
            cfg.resolve_references()
        """
        _LOGGER.verbose("Config.resolve_references: keys={}", list(self._data.keys()))
        _LOGGER.trace("pre-resolve: {}", self._data)
        self._resolve_dict(self._data, depth=0)
        _LOGGER.verbose(
            "Config.resolve_references complete | keys={}",
            list(self._data.keys()),
        )

    # -- reference resolution (private) ------------------------------------

    def _resolve_dict(self, data: dict[str, Any], *, depth: int) -> None:
        if depth > _MAX_RESOLVE_DEPTH:
            _LOGGER.warning(
                "Config._resolve_dict | depth={} | max_depth_exceeded=true",
                depth,
            )
            raise RecursionError(
                f"Reference resolution exceeded max depth ({_MAX_RESOLVE_DEPTH}). "
                "Check for circular references."
            )

        # handle __extends__ first — inherit from the referenced dict
        if "__extends__" in data:
            parent_ref = data.pop("__extends__")
            _LOGGER.trace("__extends__: {}", parent_ref)
            parent = self._resolve_value(parent_ref, depth=depth)
            if not isinstance(parent, dict):
                _LOGGER.warning(
                    "Config._resolve_dict | extends_ref={} | invalid_parent_type={}",
                    parent_ref,
                    type(parent).__name__,
                )
                raise TypeError(
                    f"__extends__ must resolve to a dict, got {type(parent).__name__}"
                )
            merged = DictUtils.merge({}, cast(dict[str, Any], parent), data)
            data.clear()
            data.update(merged)

        for key, value in data.items():
            if isinstance(value, dict):
                self._resolve_dict(cast(dict[str, Any], value), depth=depth + 1)
            elif isinstance(value, list):
                data[key] = self._resolve_list(cast(list[Any], value), depth=depth + 1)
            elif isinstance(value, str) and _is_reference(value):
                data[key] = self._resolve_value(value, depth=depth + 1)

    def _resolve_list(self, items: list[Any], *, depth: int) -> list[Any]:
        if depth > _MAX_RESOLVE_DEPTH:
            _LOGGER.warning(
                "Config._resolve_list | depth={} | max_depth_exceeded=true",
                depth,
            )
            raise RecursionError(
                f"Reference resolution exceeded max depth ({_MAX_RESOLVE_DEPTH}). "
                "Check for circular references."
            )

        result: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                self._resolve_dict(cast(dict[str, Any], item), depth=depth + 1)
                result.append(item)
            elif isinstance(item, list):
                result.append(
                    self._resolve_list(cast(list[Any], item), depth=depth + 1)
                )
            elif isinstance(item, str) and _is_reference(item):
                resolved = self._resolve_value(item, depth=depth + 1)
                # #{} list references are flattened into the parent list
                if _REF_LIST_PATTERN.match(item) and isinstance(resolved, list):
                    result.extend(cast(list[Any], resolved))
                else:
                    result.append(resolved)
            else:
                result.append(item)
        return result

    def _resolve_value(self, value: str, *, depth: int) -> Any:
        """Resolve a single string that may contain one or more references."""
        if depth > _MAX_RESOLVE_DEPTH:
            _LOGGER.warning(
                "Config._resolve_value | value={} | depth={} | max_depth_exceeded=true",
                value,
                depth,
            )
            raise RecursionError(
                f"Reference resolution exceeded max depth ({_MAX_RESOLVE_DEPTH}). "
                "Check for circular references."
            )

        resolved = self._expand_value_placeholders(value)

        if not isinstance(resolved, str):
            return resolved

        for pattern, kind in (
            (_REF_DICT_PATTERN, "dict"),
            (_REF_LIST_PATTERN, "list"),
        ):
            whole_ref = self._resolve_whole_string_ref(resolved, pattern, kind)
            if whole_ref is not _SENTINEL:
                return whole_ref

        return resolved

    def _expand_value_placeholders(self, value: str) -> Any:
        """Iteratively expand all ``${}`` placeholders in *value*.

        Returns the fully substituted string, or the referenced value itself
        (with its original type preserved) when *value* is a single
        placeholder.
        """
        resolved: Any = value

        for _ in range(_MAX_RESOLVE_DEPTH):
            if not isinstance(resolved, str) or not _REF_VALUE_PATTERN.search(resolved):
                return resolved

            made_progress = False
            ref_paths = _REF_VALUE_PATTERN.findall(resolved)
            _LOGGER.trace("Value References: {} | {}", resolved, ref_paths)
            for ref_path in ref_paths:
                resolved, made_progress = self._substitute_value_ref(
                    resolved, ref_path, made_progress
                )
                if not isinstance(resolved, str):
                    return resolved

            if not made_progress:
                return resolved  # no placeholder was resolvable — stop

        raise RecursionError(
            f"Reference resolution exceeded max depth ({_MAX_RESOLVE_DEPTH}). "
            "Check for circular references."
        )

    def _substitute_value_ref(
        self, resolved: str, ref_path: str, made_progress: bool
    ) -> tuple[Any, bool]:
        """Substitute a single ``${ref_path}`` placeholder into *resolved*."""
        placeholder = f"${{{ref_path}}}"
        ref_value = DictUtils.get(self._data, ref_path, default=_SENTINEL)
        _LOGGER.trace("Referenced Value: {} | {}", ref_path, ref_value)
        if ref_value is _SENTINEL:
            _LOGGER.warning(
                "Config._resolve_value | unresolved_placeholder={}",
                placeholder,
            )
            return resolved, made_progress  # unresolvable placeholder — skip it

        if placeholder == resolved:
            # entire string is one reference — preserve the resolved type
            return ref_value, True

        # partial substitution — coerce to string
        replaced = resolved.replace(placeholder, str(ref_value))
        _LOGGER.trace("Post Substitution: {} | {}", resolved, replaced)
        return replaced, True

    def _resolve_whole_string_ref(
        self, resolved: str, pattern: re.Pattern[str], kind: str
    ) -> Any:
        """Resolve a whole-string ``@{}``/``#{}`` reference.

        Returns ``_SENTINEL`` when *resolved* does not match *pattern* at all
        (caller should try the next reference kind); otherwise returns the
        referenced value, or *resolved* unchanged if the reference path is
        absent from the configuration.
        """
        m = pattern.match(resolved)
        if not m:
            return _SENTINEL
        ref = DictUtils.get(self._data, m.group(1), default=_SENTINEL)
        if ref is _SENTINEL:
            _LOGGER.warning(
                "Config._resolve_value | unresolved_{}_ref={}", kind, m.group(1)
            )
            return resolved
        _LOGGER.trace("Config._resolve_value | resolved_{}_ref={}", kind, m.group(1))
        return ref

    # -- dunder protocols --------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        """Return the top-level value for *key* (no dot-path support).

        Args:
            key: A top-level key in the configuration dict.

        Returns:
            The value at *key*.

        Raises:
            KeyError: If *key* is not present.
        """
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        """Return ``True`` if *key* is a top-level key in the configuration.

        Args:
            key: The key to test.

        Returns:
            ``True`` if *key* exists at the top level, ``False`` otherwise.
        """
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        """Iterate over top-level keys in the configuration.

        Returns:
            An iterator over top-level key strings.
        """
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of top-level keys in the configuration.

        Returns:
            An integer count of top-level keys.
        """
        return len(self._data)

    def __repr__(self) -> str:
        """Return an unambiguous string representation of this :class:`Config`.

        Returns:
            A string of the form ``Config({...})``.
        """
        return f"Config({self._data!r})"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_reference(value: str) -> bool:
    """Return True if *value* contains any reference syntax."""
    if (
        _REF_DICT_PATTERN.match(value) or _REF_LIST_PATTERN.match(value)
    ) and _REF_VALUE_PATTERN.search(value):
        _LOGGER.warning(
            "Nested references are discouraged due to complexity: {} | {}",
            value,
            _REF_VALUE_PATTERN.findall(value),
        )
    return bool(
        _REF_DICT_PATTERN.match(value)
        or _REF_LIST_PATTERN.match(value)
        or _REF_VALUE_PATTERN.search(value)
    )


__all__ = ["Config"]
