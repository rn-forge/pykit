"""Internal typing helpers for rn-forge Django integration boundaries.

This module is the single place where Django/django-stubs typing gaps are
absorbed, so a Django or django-stubs upgrade has one file to revisit.

Two kinds of helper live here:

- **Protocols** — structural stand-ins for Django objects that are untyped or
  awkward to name at a call boundary.
- **Generic aliases** — Django's field generics exist only in django-stubs; the
  runtime classes are not subscriptable. Every alias below is therefore declared
  under ``TYPE_CHECKING``, with a plain runtime fallback for the ones used as
  base classes. Using ``django_stubs_ext.monkeypatch()`` instead would make
  django-stubs a *runtime* dependency of this library, which we deliberately
  avoid.

This module is imported by ``models.base``, so it must stay import-light: it
must not pull in ``django.contrib.admin`` or anything else that touches the app
registry at import time. Admin-related aliases live in ``auth._typing``.
"""

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
