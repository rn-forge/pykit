"""Shared credential abstractions for rn-forge auth."""

from __future__ import annotations

from collections.abc import Sequence

from rn_forge.django._typing import AbstractUserProtocol

__all__ = [
    "BaseCredentials",
]


class BaseCredentials:
    """Base auth credential wrapper shared by rn-forge auth integrations."""

    user: object
    auth: object

    def __init__(self, user: object, auth: object) -> None:
        self.user = user
        self.auth = auth

    @property
    def is_authenticated(self) -> bool:
        """Return whether the wrapped user is authenticated."""
        return bool(getattr(self.user, "is_authenticated", False))

    @property
    def is_staff_user(self) -> bool:
        """Return whether the wrapped user should bypass permission checks."""
        return bool(
            self.is_authenticated
            and (
                getattr(self.user, "is_staff", False)
                or getattr(self.user, "is_superuser", False)
            )
        )

    @property
    def user_id(self) -> str | None:
        """Return the wrapped user identifier when available."""
        user_id = getattr(self.user, "id", getattr(self.user, "pk", None))
        return None if user_id in {None, ""} else str(user_id)

    @property
    def email(self) -> str | None:
        """Return the wrapped user email when available."""
        email = getattr(self.user, "email", None)
        return None if email in {None, ""} else str(email)

    def has_permission(self, permission: str) -> bool:
        """Return whether this credential grants *permission*."""
        if self.is_staff_user:
            return True
        if not self.is_authenticated:
            return False
        user = self.user
        if isinstance(user, AbstractUserProtocol):
            return user.has_permission(permission)
        has_permission = getattr(user, "has_permission", None)
        if callable(has_permission):
            return bool(has_permission(permission))
        return False

    def has_any_permission(self, permissions: Sequence[str]) -> bool:
        """Return whether this credential grants any permission in *permissions*."""
        if self.is_staff_user:
            return True
        return any(self.has_permission(permission) for permission in permissions)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"user_id={self.user_id!r}, "
            f"email={self.email!r}, "
            f"is_authenticated={self.is_authenticated!r})"
        )
