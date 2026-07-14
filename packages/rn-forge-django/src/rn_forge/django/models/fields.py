"""Custom Django model fields for rn-forge-django."""

from __future__ import annotations

from typing import Any

from django.db import models

from .enums import BaseEnum

__all__ = ["EnumField"]


class EnumField(models.CharField):
    """CharField that round-trips values through a ``BaseEnum`` subclass."""

    _enum_type: type[BaseEnum]

    @property
    def enum_type(self) -> type[BaseEnum]:
        """Return the enum class bound to this field."""
        return self._enum_type

    @classmethod
    def build(
        cls,
        *,
        enum_type: type[BaseEnum],
        default: BaseEnum | None = None,
        **kwargs: object,
    ) -> "EnumField":
        """Build an enum-backed field with sensible defaults."""
        kwargs.setdefault("choices", enum_type)
        kwargs.setdefault("default", default.value if default else None)
        kwargs.setdefault("max_length", max(len(item.value) for item in enum_type))

        instance = cls(**kwargs)
        instance._enum_type = enum_type
        return instance

    def from_db_value(
        self,
        value: Any,
        expression: object,
        connection: object,
    ) -> BaseEnum | None:
        """Convert raw database values to enum members."""
        del expression, connection
        if value is None:
            return None
        return self.enum_type(value)

    def to_python(self, value: Any) -> BaseEnum | None:
        """Convert assigned values to enum members when possible."""
        if value is None or isinstance(value, self.enum_type):
            return value
        return self.enum_type(value)

    def get_prep_value(self, value: Any) -> str | None:
        """Convert enum members to their raw database values."""
        if value is None:
            return None
        if isinstance(value, self.enum_type):
            return value.value
        return str(value)
