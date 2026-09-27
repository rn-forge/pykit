"""Internal protocols and runtime-safe aliases for Django types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeAlias, runtime_checkable

from django.db import models

__all__ = [
    "AbstractUserProtocol",
    "DateField",
    "DjangoAuthProtocol",
    "EnumFieldBase",
    "NullableDateField",
    "StrField",
    "TimestampField",
]


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class AbstractUserProtocol(Protocol):
    """Typed proxy for user-like auth objects used by credential helpers."""

    is_authenticated: bool
    is_staff: bool
    is_superuser: bool
    email: str
    id: object
    pk: object

    def has_permission(self, permission: str) -> bool: ...


class DjangoAuthProtocol(Protocol):
    """Typed proxy for the ``django.contrib.auth`` functions used here."""

    def authenticate(self, *args: object, **kwargs: object) -> object | None: ...

    def login(self, request: object, user: object) -> None: ...

    def logout(self, request: object) -> None: ...


# ---------------------------------------------------------------------------
# django-stubs generic aliases
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from datetime import date, datetime

    from .models.enums import BaseEnum

    # ``Field[_ST, _GT]`` names the assignable type and the type read back off a
    # model instance.
    type StrField = models.CharField[str, str]
    type TimestampField = models.DateTimeField[datetime, datetime]
    type DateField = models.DateField[date, date]
    type NullableDateField = models.DateField[date | None, date | None]
    # Used as an EnumField base class below, so it must stay a TypeAlias — a
    # PEP 695 "type" statement alias cannot be subclassed.
    EnumFieldBase: TypeAlias = models.CharField[
        BaseEnum | str | None, BaseEnum | None
    ]  # NOSONAR(S6794)
else:
    # Runtime fallbacks: the unsubscripted classes. Every alias gets one so that
    # consumers can use a single plain import rather than repeating a
    # ``TYPE_CHECKING`` guard at each site.
    StrField = models.CharField
    TimestampField = models.DateTimeField
    DateField = models.DateField
    NullableDateField = models.DateField
    EnumFieldBase = models.CharField
