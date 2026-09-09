"""Serialisation and round-trip config documents: JSON, YAML, and TOML.

Provides:

- :class:`JsonUtils` — JSON load/serialize/file I/O with dataclass-aware
  serialisation and sensible defaults.
- :class:`YamlUtils` — YAML load/serialize/file I/O with multi-document
  support.
- :class:`ConfigFormat` — TOML/YAML/JSON, resolved from a path suffix.
- :class:`DocumentUtils` — suffix-dispatched plain-mapping I/O (comments
  discarded) and round-trip document I/O (comments and formatting preserved).
- :class:`DocumentError` — raised on an unreadable, unparsable, or
  non-mapping-rooted document.

**One YAML backend.** ``ruamel.yaml`` handles every YAML path in this
package: ``typ="safe"`` for plain loads and dumps, ``typ="rt"`` only where
comments and formatting must survive an edit. ``pyyaml`` is not a dependency
— ruamel is a functional superset of it, and running two YAML parsers with
divergent behaviour in one package is worse than the one dependency swap.
The trade-off is that ruamel's ``load``/``dump`` are typed as partially
unknown, so calls go through :func:`_yaml_load` / :func:`_yaml_dump`, which
own the required ``cast`` in one place rather than scattering it across
call sites.

TOML uses ``tomlkit`` rather than stdlib ``tomllib``: ``tomllib`` reads TOML
but cannot write it, and cannot preserve comments across an edit.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum, StrEnum
from io import StringIO
from pathlib import Path, PurePath
from typing import Any, Self, cast

import tomlkit
from ruamel.yaml import YAML

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.utils import PathUtils

_LOGGER = AppLogger.get_logger(__name__)

__all__ = [
    "ConfigFormat",
    "DocumentError",
    "DocumentUtils",
    "JsonUtils",
    "YamlUtils",
]


class DocumentError(AppException):
    """A configuration document cannot be read, parsed, or encoded."""


class ConfigFormat(StrEnum):
    """A configuration document's serialization format."""

    TOML = "toml"
    YAML = "yaml"
    JSON = "json"

    @classmethod
    def of(cls, path: Path, override: str | None = None) -> Self:
        """Resolve the format from *path*'s suffix, or *override* if given.

        ``.yml`` is treated as an alias for ``yaml``.

        Raises:
            DocumentError: The resolved suffix does not match a known format.
        """
        raw = (override or path.suffix.lstrip(".")).lower()
        raw = "yaml" if raw == "yml" else raw
        try:
            return cls(raw)
        except ValueError:
            raise DocumentError(f"Unsupported document format: {raw!r}") from None


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
# YamlUtils — YAML load / serialize / file I/O (safe mode, ruamel.yaml)
# ---------------------------------------------------------------------------


class YamlUtils:
    """YAML helpers with multi-document support and file I/O.

    Backed by ``ruamel.yaml`` in ``typ="safe"`` mode: only standard YAML tags
    are loaded and emitted, so untrusted input cannot instantiate arbitrary
    Python objects. Use :class:`DocumentUtils` when comments and formatting
    must survive a round trip.
    """

    @staticmethod
    def load(text: str, *, root_key: str | None = None) -> Any:
        """Parse a YAML string and return the resulting Python object.

        Args:
            text: Raw YAML text.
            root_key: When provided, return only the value at this top-level
                key from the parsed document.

        Returns:
            The parsed Python object, or the value at *root_key* if given.
            An empty document yields ``None``.

        Raises:
            ruamel.yaml.YAMLError: If *text* is not valid YAML.
            KeyError: If *root_key* is provided but absent from the parsed
                document.
        """
        _LOGGER.trace(
            "YamlUtils.load | root_key={} | text_length={}", root_key, len(text)
        )
        try:
            obj = _yaml_load(_safe_yaml(), text)
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

        Args:
            text: Raw YAML text containing one or more ``---``-separated
                documents.

        Returns:
            A list of parsed Python objects, one per non-empty document.

        Raises:
            ruamel.yaml.YAMLError: If *text* is not valid YAML.
        """
        _LOGGER.trace("YamlUtils.load_all | text_length={}", len(text))
        try:
            docs = _yaml_load_all(_safe_yaml(), text)
        except Exception:
            _LOGGER.exception("YamlUtils.load_all failed | text_length={}", len(text))
            raise
        return [doc for doc in docs if doc is not None]

    @staticmethod
    def serialize(obj: Any, *, sort_keys: bool = False, **kwargs: Any) -> str:
        """Serialise *obj* to a YAML string.

        Args:
            obj: The Python object to serialise. Only standard YAML types are
                supported; dataclasses must be converted first (e.g. via
                :meth:`~rn_forge.commons.dataclasses.DataclassMixin.as_dict`).
            sort_keys: Sort mapping keys in the output. Defaults to ``False``,
                preserving insertion order.
            **kwargs: Set as attributes on the underlying ``ruamel.yaml.YAML``
                instance (e.g. ``indent``, ``width``, ``allow_unicode``,
                ``default_flow_style``).

        Returns:
            The YAML representation of *obj*, block-style by default.

        Raises:
            ruamel.yaml.YAMLError: If *obj* contains a type the safe
                representer cannot emit.
        """
        _LOGGER.trace(
            "YamlUtils.serialize | type={} | sort_keys={}",
            type(obj).__name__,
            sort_keys,
        )
        yaml = _safe_yaml(sort_keys=sort_keys, **kwargs)
        stream = StringIO()
        try:
            _yaml_dump(yaml, obj, stream)
        except Exception:
            _LOGGER.exception(
                "YamlUtils.serialize failed | type={}", type(obj).__name__
            )
            raise
        return stream.getvalue()

    @staticmethod
    def serialize_all(*objs: Any, sort_keys: bool = False, **kwargs: Any) -> str:
        """Serialise *objs* to a single multi-document YAML string.

        Args:
            *objs: The Python objects to serialise, one document each.
            sort_keys: Sort mapping keys in the output. Defaults to ``False``.
            **kwargs: Set as attributes on the underlying ``ruamel.yaml.YAML``
                instance.

        Returns:
            The ``---``-separated YAML representation of *objs*.

        Raises:
            ruamel.yaml.YAMLError: If any object contains a type the safe
                representer cannot emit.
        """
        _LOGGER.trace("YamlUtils.serialize_all | count={}", len(objs))
        yaml = _safe_yaml(sort_keys=sort_keys, **kwargs)
        stream = StringIO()
        try:
            _yaml_dump_all(yaml, objs, stream)
        except Exception:
            _LOGGER.exception("YamlUtils.serialize_all failed | count={}", len(objs))
            raise
        return stream.getvalue()

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
# DocumentUtils — suffix-dispatched plain and round-trip document I/O
# ---------------------------------------------------------------------------


class DocumentUtils:
    """Config documents addressed by path, with an optional round-trip mode.

    The *plain* methods (:meth:`loads`, :meth:`dumps`, :meth:`read`,
    :meth:`write`) produce ordinary ``dict``/``list``/scalar trees and discard
    comments. The *document* methods (:meth:`read_document`,
    :meth:`write_document`, :meth:`update`) keep the backing library's own
    containers, so comments and formatting survive an edit.

    All methods are static.
    """

    # -- plain mappings (comments discarded) --------------------------------

    @staticmethod
    def loads(text: str, fmt: ConfigFormat | str) -> dict[str, Any]:
        """Parse *text* in format *fmt* into a plain, comment-free mapping.

        Raises:
            DocumentError: *text* is invalid for *fmt*, or its root is not a
                mapping.
        """
        fmt = ConfigFormat(fmt)
        try:
            match fmt:
                case ConfigFormat.TOML:
                    value: Any = tomlkit.loads(text).unwrap()
                case ConfigFormat.YAML:
                    value = YamlUtils.load(text)
                    if value is None:
                        value = {}
                case ConfigFormat.JSON:
                    value = JsonUtils.load(text)
        except Exception as exc:
            raise DocumentError(f"Invalid {fmt.value.upper()} document: {exc}") from exc
        if not isinstance(value, Mapping):
            raise DocumentError("Document root must be a mapping")
        return _to_plain_mapping(cast(Mapping[Any, Any], value))

    @staticmethod
    def dumps(data: Mapping[str, Any], fmt: ConfigFormat | str) -> str:
        """Serialize *data* in format *fmt*, in a stable, human-readable form."""
        fmt = ConfigFormat(fmt)
        plain = _to_plain_mapping(data)
        match fmt:
            case ConfigFormat.TOML:
                return tomlkit.dumps(plain)
            case ConfigFormat.YAML:
                return YamlUtils.serialize(plain, default_flow_style=False)
            case ConfigFormat.JSON:
                return json.dumps(plain, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def read(path: str | Path, *, missing_ok: bool = False) -> dict[str, Any]:
        """Read and parse the document at *path* into a plain mapping.

        Args:
            path: The document file.
            missing_ok: When ``True``, a missing file returns ``{}`` instead
                of raising.

        Raises:
            DocumentError: *path* does not exist (and ``missing_ok=False``),
                or the document is invalid.
        """
        p = Path(path)
        if not p.exists():
            if missing_ok:
                return {}
            raise DocumentError(f"Document does not exist: {p}")
        return DocumentUtils.loads(p.read_text(encoding="utf-8"), ConfigFormat.of(p))

    @staticmethod
    def write(path: str | Path, data: Mapping[str, Any]) -> None:
        """Atomically write *data* to *path*, formatted per its suffix."""
        p = Path(path)
        PathUtils.atomic_write(DocumentUtils.dumps(data, ConfigFormat.of(p)), p)

    # -- round-trip documents (comments and style preserved) -----------------

    @staticmethod
    def read_document(path: str | Path) -> Any:
        """Read *path* as a round-trip document, preserving comments and style.

        Raises:
            DocumentError: The document is invalid for its resolved format or
                its root is not a mapping.
        """
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        fmt = ConfigFormat.of(p)
        try:
            match fmt:
                case ConfigFormat.TOML:
                    document: Any = tomlkit.loads(text)
                case ConfigFormat.YAML:
                    document = _yaml_load(_round_trip_yaml(), text)
                    if document is None:
                        document = {}
                case ConfigFormat.JSON:
                    document = json.loads(text)
        except Exception as exc:
            raise DocumentError(f"Invalid document {p}: {exc}") from exc
        if not isinstance(document, Mapping):
            raise DocumentError(f"Document root must be a mapping: {p}")
        return cast(Mapping[str, Any], document)

    @staticmethod
    def write_document(path: str | Path, document: Any) -> None:
        """Atomically write a round-trip *document* without flattening it."""
        p = Path(path)
        fmt = ConfigFormat.of(p)
        match fmt:
            case ConfigFormat.TOML:
                content = tomlkit.dumps(document)
            case ConfigFormat.YAML:
                stream = StringIO()
                _yaml_dump(_round_trip_yaml(), document, stream)
                content = stream.getvalue()
            case ConfigFormat.JSON:
                content = json.dumps(document, indent=2, sort_keys=True) + "\n"
        PathUtils.atomic_write(content, p)

    @staticmethod
    def update(path: str | Path, updates: Mapping[str, Any]) -> None:
        """Deep-update the document at *path* with *updates*, preserving comments.

        Creates *path* (via :meth:`write`) if it does not yet exist.

        Raises:
            DocumentError: The existing document's root is not a mutable
                mapping.
        """
        p = Path(path)
        if not p.exists():
            DocumentUtils.write(p, updates)
            return
        document = DocumentUtils.read_document(p)
        if not isinstance(document, MutableMapping):
            raise DocumentError("Document root must be a mutable mapping")
        _deep_update_document(cast(MutableMapping[str, Any], document), updates)
        DocumentUtils.write_document(p, document)

    @staticmethod
    def append_to_array(document: Any, key: str, fields: Mapping[str, Any]) -> None:
        """Append one table built from *fields* to the array-of-tables at *key*.

        Creates the array if *key* is absent. Intended for TOML documents —
        appending to an array-of-tables without disturbing surrounding
        comments is fiddly enough to be worth solving once.
        """
        table = tomlkit.table()
        for field_key, value in fields.items():
            if value is not None:
                table[field_key] = value
        existing: Any = document.get(key)
        if existing is None:
            array_of_tables: Any = tomlkit.aot()
            array_of_tables.append(table)
            document[key] = array_of_tables
        else:
            existing.append(table)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _safe_yaml(*, sort_keys: bool = False, **kwargs: Any) -> YAML:
    """Build a safe-mode ``YAML`` instance, block-style and insertion-ordered."""
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.representer.sort_base_mapping_type_on_output = sort_keys
    for name, value in kwargs.items():
        setattr(yaml, name, value)
    return yaml


def _round_trip_yaml() -> YAML:
    """Build a round-trip ``YAML`` instance that preserves comments and style."""
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    return yaml


def _yaml_load(yaml: YAML, text: str) -> Any:
    """Load one YAML document. Isolates ruamel's partially-unknown ``load`` type."""
    return cast(Any, yaml).load(text)


def _yaml_load_all(yaml: YAML, text: str) -> list[Any]:
    """Load every YAML document in *text*."""
    return list(cast(Any, yaml).load_all(text))


def _yaml_dump(yaml: YAML, data: object, stream: StringIO) -> None:
    """Dump one YAML document. Isolates ruamel's partially-unknown ``dump`` type."""
    cast(Any, yaml).dump(data, stream)


def _yaml_dump_all(yaml: YAML, documents: tuple[Any, ...], stream: StringIO) -> None:
    """Dump *documents* as a ``---``-separated YAML stream."""
    cast(Any, yaml).dump_all(documents, stream)


def _to_plain(value: Any) -> Any:
    """Recursively coerce a tomlkit/ruamel container tree into plain dict/list/scalars."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        return {str(key): _to_plain(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        sequence = cast("list[Any] | tuple[Any, ...]", value)
        return [_to_plain(item) for item in sequence]
    return value


def _to_plain_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], _to_plain(value))


def _deep_update_document(
    target: MutableMapping[str, Any], updates: Mapping[str, Any]
) -> None:
    """Deep-merge *updates* into *target* in place, preserving untouched keys' comments.

    Deliberately not :meth:`~rn_forge.commons.collections.DictUtils.merge`:
    that helper is ``dict``-typed and deep-copies override values, which would
    replace the tomlkit/ruamel containers here with plain ones and discard the
    comments attached to them.
    """
    for key, value in updates.items():
        current = target.get(key)
        if isinstance(current, MutableMapping) and isinstance(value, Mapping):
            _deep_update_document(
                cast(MutableMapping[str, Any], current), cast(Mapping[str, Any], value)
            )
        else:
            target[key] = value


def _json_default(obj: object) -> Any:
    """Default JSON serialiser.

    dataclass -> dict, ``PurePath`` -> str, ``Enum`` -> its value,
    date/datetime/time -> ISO 8601, set/frozenset -> sorted list,
    ``Decimal`` -> float, otherwise ``repr()``.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, PurePath):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        items: list[Any] = list(cast(set[Any], obj))
        return sorted(items, key=repr)
    if isinstance(obj, Decimal):
        return float(obj)
    return repr(obj)
