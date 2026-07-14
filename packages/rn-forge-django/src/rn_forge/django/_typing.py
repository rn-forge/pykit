"""Internal typing helpers for rn-forge Django integration boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = [
    "AbstractUserProtocol",
    "DjangoAuthProtocol",
]


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
