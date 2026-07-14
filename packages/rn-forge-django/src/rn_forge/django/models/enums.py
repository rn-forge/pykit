"""Model-specific enum types for rn-forge-django."""

from __future__ import annotations

from django.db import models

__all__ = [
    "BaseEnum",
    "Status",
]


class BaseEnum(models.TextChoices):
    """TextChoices subclass with reverse-lookup helpers."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls._lookup = {str(value): key for key, value in cls.__members__.items()}

    @classmethod
    def get_choices(
        cls,
        code_filter: list[str] | None = None,
        name_filter: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Return a list of ``{"code": ..., "name": ...}`` dicts."""
        return [
            {"code": code, "name": name}
            for code, name in cls._lookup.items()
            if (code_filter is None or code in code_filter)
            and (name_filter is None or name in name_filter)
        ]

    @classmethod
    def lookup(cls, key: str) -> dict[str, str]:
        """Return ``{"code": key, "name": ...}`` for the given enum value."""
        if key not in cls._lookup:
            raise ValueError(f"Invalid value for {cls.__name__}: {key!r}")

        return {"code": key, "name": cls._lookup[key]}


class Status(BaseEnum):
    """Standard record-status choices."""

    Active = "A"
    Inactive = "I"
    Error = "E"
    Deleted = "D"
    Expired = "X"
