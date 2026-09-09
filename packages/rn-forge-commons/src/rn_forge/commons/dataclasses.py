"""Dataclass mixin for serialisation and dict conversion.

Provides :class:`DataclassMixin`, a base class that adds ``as_dict()``,
``to_json()``, ``to_yaml()``, and ``from_dict()`` to any
``@dataclass``-decorated class.

Field exclusion
~~~~~~~~~~~~~~~

Mark a field with ``metadata={"exclude": True}`` to omit it from
``as_dict()`` (and therefore from JSON/YAML output)::

    @dataclass
    class User(DataclassMixin):
        name: str
        password: str = field(metadata={"exclude": True})
"""

from __future__ import annotations

import dataclasses
from typing import Any, ClassVar, Self, cast

import dacite

from rn_forge.commons.documents import JsonUtils, YamlUtils
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)


class DataclassMixin:
    """Mixin that adds serialisation helpers to a ``@dataclass``.

    Must be used together with ``@dataclasses.dataclass``.  The mixin itself
    does **not** apply the decorator — this keeps field declarations explicit
    and avoids any global side effects.

    Example::

        from dataclasses import dataclass, field
        from rn_forge.commons import DataclassMixin

        @dataclass
        class AppConfig(DataclassMixin):
            host: str = "localhost"
            port: int = 8080
            secret: str = field(default="changeme", metadata={"exclude": True})

        cfg = AppConfig()
        print(cfg.to_json())   # {"host": "localhost", "port": 8080}
        print(cfg.to_yaml())   # host: localhost\\nport: 8080\\n
    """

    def as_dict(self, *, exclude_hidden: bool = True) -> dict[str, Any]:
        """Convert this dataclass instance to a plain dict.

        Args:
            exclude_hidden: When ``True`` (default), fields decorated with
                ``metadata={"exclude": True}`` are omitted from the result,
                recursively throughout nested dataclasses.
                Pass ``False`` to include every field.

        Returns:
            A dict mapping field names to their current values. Nested
            dataclasses are recursively converted, respecting ``exclude``
            metadata at every level.

        Raises:
            TypeError: If the subclass was not decorated with
                ``@dataclasses.dataclass``.
        """
        return _dataclass_to_dict(self, exclude_hidden=exclude_hidden)

    def to_json(self, *, indent: str | int | None = None, **kwargs: Any) -> str:
        """Serialise this instance to a JSON string.

        Fields excluded via ``metadata={"exclude": True}`` are omitted.

        Args:
            indent: Indentation level passed to :func:`json.dumps`. ``None``
                produces compact output.
            **kwargs: Additional keyword arguments forwarded to
                :func:`json.dumps`.

        Returns:
            A JSON string representation of this instance.
        """
        _LOGGER.trace("DataclassMixin.to_json | cls={}", type(self).__name__)
        return JsonUtils.serialize(self.as_dict(), indent=indent, **kwargs)

    def to_yaml(self, **kwargs: Any) -> str:
        """Serialise this instance to a YAML string.

        Fields excluded via ``metadata={"exclude": True}`` are omitted.

        Args:
            **kwargs: Additional keyword arguments forwarded to
                :meth:`~rn_forge.commons.documents.YamlUtils.serialize`
                (e.g. ``sort_keys``, ``default_flow_style``).

        Returns:
            A YAML string representation of this instance.
        """
        _LOGGER.trace("DataclassMixin.to_yaml | cls={}", type(self).__name__)
        return YamlUtils.serialize(self.as_dict(), **kwargs)

    #: dacite configuration used by :meth:`from_dict`. ``check_types=False``
    #: preserves this mixin's long-standing lenient behaviour — an unmatched
    #: value (e.g. a ``str`` for an ``int``-annotated field) passes through
    #: unchanged rather than raising. ``cast=[tuple, set]`` preserves the old
    #: coercion's structural ``list -> tuple``/``list -> set`` conversion for
    #: those two container types (dacite does not cast containers by default,
    #: even with ``check_types=False``). Override in a subclass to opt into
    #: strict type checking: ``__dacite_config__ = dacite.Config(check_types=True)``.
    __dacite_config__: ClassVar[dacite.Config] = dacite.Config(
        check_types=False, cast=[tuple, set]
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create an instance from a dict, recursively rebuilding nested dataclasses.

        Only keys that match declared dataclass field names are passed to the
        constructor.  This makes ``from_dict`` tolerant of extra data (e.g.
        when loading from a config file that has fields added in a newer
        schema version). Nested dataclass-typed fields are reconstructed
        recursively for common container annotations, via :mod:`dacite`.

        Note a nested dataclass field's own overridden ``from_dict`` (if any)
        is **not** called — dacite structures nested dataclasses itself.

        Args:
            data: A dict whose keys correspond to dataclass field names.
                Unrecognised keys are silently ignored.

        Returns:
            A new instance of this class populated with matching field values.

        Raises:
            TypeError: If the subclass was not decorated with
                ``@dataclasses.dataclass``.
        """
        if not dataclasses.is_dataclass(cls):
            _LOGGER.warning(
                "DataclassMixin.from_dict: target is not a dataclass | cls={}", cls
            )
            raise TypeError(
                f"{cls.__name__} is not a dataclass — DataclassMixin requires @dataclass"
            )
        field_names = {field.name for field in dataclasses.fields(cls)}
        ignored_keys = sorted(set(data) - field_names)
        if ignored_keys:
            _LOGGER.debug(
                "DataclassMixin.from_dict: ignoring unknown keys | cls={} | keys={}",
                cls.__name__,
                ignored_keys,
            )
        try:
            return dacite.from_dict(
                data_class=cls, data=data, config=cls.__dacite_config__
            )
        except dacite.DaciteError:
            _LOGGER.exception(
                "DataclassMixin.from_dict failed | cls={} | keys={}",
                cls.__name__,
                sorted(data),
            )
            raise

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Create an instance from a JSON string.

        Delegates to :meth:`from_dict` after parsing, so unknown keys are
        ignored.

        Args:
            text: A JSON string representing a dict of field values.

        Returns:
            A new instance populated from the parsed JSON.

        Raises:
            json.JSONDecodeError: If *text* is not valid JSON.
        """
        _LOGGER.trace(
            "DataclassMixin.from_json | cls={} | text_length={}",
            cls.__name__,
            len(text),
        )
        return cls.from_dict(JsonUtils.load(text))

    @classmethod
    def from_yaml(cls, text: str) -> Self:
        """Create an instance from a YAML string.

        Delegates to :meth:`from_dict` after parsing, so unknown keys are
        ignored.

        Args:
            text: A YAML string representing a mapping of field values.

        Returns:
            A new instance populated from the parsed YAML.

        Raises:
            ruamel.yaml.YAMLError: If *text* is not valid YAML.
        """
        _LOGGER.trace(
            "DataclassMixin.from_yaml | cls={} | text_length={}",
            cls.__name__,
            len(text),
        )
        return cls.from_dict(YamlUtils.load(text))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Set mixin __str__/__repr__ before @dataclass runs (which checks cls.__dict__
        # and skips generation if they're already present). Only overwrite when the
        # subclass hasn't explicitly defined its own version.
        if "__str__" not in cls.__dict__:
            cls.__str__ = DataclassMixin.__str__
        if "__repr__" not in cls.__dict__:
            cls.__repr__ = DataclassMixin.__repr__

    def __str__(self) -> str:
        """Return a JSON string representation of this instance.

        Equivalent to calling :meth:`to_json`.  Excluded fields are omitted.

        Returns:
            A compact JSON string (no indentation).
        """
        return self.to_json()

    def __repr__(self) -> str:
        """Return an unambiguous ``ClassName(field=value, ...)`` representation.

        Excluded fields (``metadata={"exclude": True}``) are omitted.  Falls
        back to :func:`object.__repr__` when the class is not a dataclass.

        Returns:
            A string of the form ``ClassName(field1=value1, field2=value2)``.
        """
        if not dataclasses.is_dataclass(self):
            return super().__repr__()
        parts = ", ".join(
            f"{f.name}={getattr(self, f.name)!r}"
            for f in dataclasses.fields(self)
            if not f.metadata.get("exclude", False)
        )
        return f"{type(self).__name__}({parts})"


__all__ = ["DataclassMixin"]


def _dataclass_to_dict(obj: Any, *, exclude_hidden: bool) -> dict[str, Any]:
    """Recursively convert a dataclass to a dict, respecting ``exclude`` metadata."""
    if not dataclasses.is_dataclass(obj):
        _LOGGER.warning(
            "_dataclass_to_dict: target is not a dataclass | type={}",
            type(obj).__name__,
        )
        raise TypeError(
            f"{type(obj).__name__} is not a dataclass — DataclassMixin requires @dataclass"
        )
    result: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        if exclude_hidden and f.metadata.get("exclude", False):
            _LOGGER.trace(
                "_dataclass_to_dict | cls={} | excluded_field={}",
                type(obj).__name__,
                f.name,
            )
            continue
        result[f.name] = _convert_value(
            getattr(obj, f.name), exclude_hidden=exclude_hidden
        )
    return result


def _convert_value(value: Any, *, exclude_hidden: bool) -> Any:
    """Recursively convert a value, expanding nested dataclasses."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _dataclass_to_dict(value, exclude_hidden=exclude_hidden)
    if isinstance(value, list):
        return [
            _convert_value(item, exclude_hidden=exclude_hidden)
            for item in cast(list[Any], value)
        ]
    if isinstance(value, tuple):
        return tuple(
            _convert_value(item, exclude_hidden=exclude_hidden)
            for item in cast(tuple[Any, ...], value)
        )
    if isinstance(value, frozenset):
        return frozenset(
            _convert_value(item, exclude_hidden=exclude_hidden)
            for item in cast(frozenset[Any], value)
        )
    if isinstance(value, set):
        return {
            _convert_value(item, exclude_hidden=exclude_hidden)
            for item in cast(set[Any], value)
        }
    if isinstance(value, dict):
        return {
            k: _convert_value(v, exclude_hidden=exclude_hidden)
            for k, v in cast(dict[Any, Any], value).items()
        }
    return value
