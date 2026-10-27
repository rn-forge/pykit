"""The ``/auth/session`` response body and the callback error codes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, get_args

from rn_forge.auth.context import AuthorizationContext
from rn_forge.auth.identity import SessionInfo

__all__ = ["CALLBACK_ERRORS", "CallbackError", "SessionBody"]

CallbackError = Literal["access_denied", "account_not_provisioned", "login_failed"]
"""The codes a failed login callback sends to the error route."""

CALLBACK_ERRORS: frozenset[str] = frozenset(get_args(CallbackError))
"""The members of :data:`CallbackError`."""


@dataclass(frozen=True)
class SessionBody:
    """The signed-in user as the SPA sees it.

    Attributes:
        subject: The internal account ID, never the external subject.
        provider: ID of the provider that authenticated the session.
        roles: Role names.
        permissions: Permission keys.
        expires_at: When the absolute timeout ends the session.
        name: Display name.
        email: Email address.
        picture: Avatar URL.
        attributes: Application-defined values for the UI.
        auth_time: When the user authenticated.
        amr: How the user authenticated.
    """

    subject: str
    provider: str
    expires_at: datetime
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    name: str | None = None
    email: str | None = None
    picture: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])
    auth_time: datetime | None = None
    amr: frozenset[str] = frozenset()

    @classmethod
    def build(
        cls,
        session: SessionInfo,
        context: AuthorizationContext,
        *,
        name: str | None = None,
        email: str | None = None,
        picture: str | None = None,
    ) -> SessionBody:
        """Combine a session, its authorization context and profile values."""
        return cls(
            subject=session.account_id,
            provider=session.provider,
            expires_at=session.expires_at,
            roles=context.roles,
            permissions=context.permissions,
            name=name,
            email=email,
            picture=picture,
            attributes=context.attributes,
            auth_time=session.auth_time,
            amr=session.amr,
        )

    def to_json(self) -> dict[str, Any]:
        """Return the camelCase wire body.

        Datetimes are RFC 3339 UTC strings ending in ``Z``. ``roles``,
        ``permissions`` and ``amr`` are sorted lists. ``name``, ``email``,
        ``picture``, ``authTime``, ``attributes`` and ``amr`` are omitted when
        absent or empty. Keys of ``attributes``, at every depth, are converted
        from snake_case to camelCase.
        """
        body: dict[str, Any] = {
            "subject": self.subject,
            "name": self.name,
            "email": self.email,
            "picture": self.picture,
            "provider": self.provider,
            "roles": sorted(self.roles),
            "permissions": sorted(self.permissions),
            "attributes": _camelize(self.attributes) if self.attributes else None,
            "authTime": _rfc3339(self.auth_time) if self.auth_time else None,
            "amr": sorted(self.amr) or None,
            "expiresAt": _rfc3339(self.expires_at),
        }
        return {key: value for key, value in body.items() if value is not None}


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _camel_key(key: str) -> str:
    head = key.lstrip("_")
    lead = key[: len(key) - len(head)]
    first, *rest = head.split("_")
    return lead + first + "".join(part[:1].upper() + part[1:] for part in rest)


def _camelize(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapping: Mapping[Any, Any] = value  # pyright: ignore[reportUnknownVariableType]
        return {
            _camel_key(k) if isinstance(k, str) else k: _camelize(v)
            for k, v in mapping.items()
        }
    if isinstance(value, (list, tuple)):
        items: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
        return [_camelize(item) for item in items]
    return value
