"""JWT-backed credentials for rn-forge auth."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from rn_forge.django.auth.credentials import BaseCredentials

__all__ = ["JWTCredentials"]


class JWTCredentials(BaseCredentials):
    """Credentials wrapper backed by a validated JWT token."""

    @property
    def payload(self) -> Mapping[str, object]:
        """Return the validated token payload."""

        auth = self.auth
        if hasattr(auth, "payload"):
            payload = getattr(auth, "payload")
            if isinstance(payload, Mapping):
                return cast(Mapping[str, object], payload)

        if isinstance(auth, Mapping):
            return cast(Mapping[str, object], auth)

        return {}

    @property
    def profile(self) -> Mapping[str, object]:
        """Return the JWT profile payload when present."""
        profile = self.payload.get("profile", {})
        return cast(
            Mapping[str, object], profile if isinstance(profile, Mapping) else {}
        )

    @property
    def permissions(self) -> tuple[str, ...]:
        """Return JWT permission keys when present."""

        permissions = self.payload.get("permissions", ())
        if not isinstance(permissions, Sequence) or isinstance(permissions, str):
            return ()

        return tuple(
            str(permission)
            for permission in cast(Sequence[object], permissions)
            if permission
        )

    @property
    def user_id(self) -> str | None:
        """Return user id from token claims or fallback to wrapped user."""

        for key in ("user_id", "sub"):
            value = self.payload.get(key)
            if value not in {None, ""}:
                return str(value)

        return super().user_id

    @property
    def email(self) -> str | None:
        """Return email from token claims or fallback to wrapped user."""
        value = self.payload.get("email")
        if value not in {None, ""}:
            return str(value)

        return super().email

    def get_claim(self, key: str, default: object | None = None) -> object | None:
        """Return one token claim."""

        return self.payload.get(key, default)

    def has_permission(self, permission: str) -> bool:
        """Return whether JWT-backed permissions grant *permission*."""

        if self.is_staff_user:
            return True

        if self.permissions:
            return permission in self.permissions

        return super().has_permission(permission)

    def has_any_permission(self, permissions: Sequence[str]) -> bool:
        """Return whether JWT-backed permissions grant any in *permissions*."""

        if self.is_staff_user:
            return True

        if self.permissions:
            permission_set = set(self.permissions)
            return any(permission in permission_set for permission in permissions)

        return super().has_any_permission(permissions)
