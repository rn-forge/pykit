"""Model serialization helpers for rn-forge-django."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from rn_forge.commons.fs.documents import JsonUtils
from ._meta import get_model_meta

from django.db import models

__all__ = ["ModelUtils"]

_PRIMITIVE_TYPES = (str, int, float, bool, type(None))
_DATETIME_TYPES = (datetime, date, time)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class ModelUtils:
    """Utilities for serialising Django model instances.

    All methods are static.
    """

    @staticmethod
    def as_json_value(value: Any) -> Any:
        """Coerce a model field value to a JSON-safe primitive.

        - Primitives (``str``, ``int``, ``float``, ``bool``, ``None``) are
          returned unchanged.
        - :class:`~datetime.datetime`, :class:`~datetime.date`, and
          :class:`~datetime.time` values are converted via ``.isoformat()``.
        - All other types fall back to ``str(value)``.
        """
        if isinstance(value, _PRIMITIVE_TYPES):
            return value
        if isinstance(value, _DATETIME_TYPES):
            return value.isoformat()
        return str(value)

    @staticmethod
    def as_dict(
        instance: models.Model,
        _seen: set[int] | None = None,
    ) -> dict[str, Any]:
        """Return a plain dict of all concrete fields on *instance*.

        Related model instances are recursively converted. Cycles are broken
        by tracking ``id()`` of visited instances; a repeated instance is
        represented as its string ``repr`` instead of being expanded again.
        """
        if _seen is None:
            _seen = set()

        _seen.add(id(instance))

        result: dict[str, Any] = {}
        for field in get_model_meta(type(instance)).concrete_fields:
            fname = field.name
            value = getattr(instance, fname)
            if isinstance(value, models.Model):
                if id(value) in _seen:
                    result[fname] = repr(value)
                else:
                    result[fname] = ModelUtils.as_dict(value, _seen)
            else:
                result[fname] = ModelUtils.as_json_value(value)

        return result

    @staticmethod
    def to_json(instance: models.Model, *, indent: int | None = None) -> str:
        """Serialise *instance* to a JSON string."""
        return JsonUtils.serialize(ModelUtils.as_dict(instance), indent=indent)
