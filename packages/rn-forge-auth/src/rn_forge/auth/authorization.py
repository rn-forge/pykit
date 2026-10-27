"""Authenticator and authorizer contracts.

Missing or invalid credentials produce a 401 challenge; an authenticated
principal without sufficient access produces 403. Verification details must
not be exposed in the 401 response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from rn_forge.auth.principal import Principal, Requirement
from rn_forge.web.auth import Credentials
from rn_forge.web.exceptions import PermissionDenied

__all__ = [
    "AsyncAuthenticator",
    "Authenticator",
    "Authorizer",
    "ScopeAuthorizer",
]


@runtime_checkable
class Authenticator(Protocol):
    """Turns raw credentials into a verified :class:`Principal`."""

    def authenticate(self, *, credentials: Credentials) -> Principal:
        """Verify *credentials*.

        Raises:
            AuthenticationFailed: The credentials are absent, malformed or
                invalid. The message must not say which.
        """
        ...


@runtime_checkable
class AsyncAuthenticator(Protocol):
    """Asynchronous counterpart of :class:`Authenticator`."""

    async def authenticate(self, *, credentials: Credentials) -> Principal:
        """See :meth:`Authenticator.authenticate`."""
        ...


@runtime_checkable
class Authorizer(Protocol):
    """Decides whether a verified principal may proceed."""

    def authorize(self, principal: Principal, *, requires: Requirement) -> None:
        """Permit the request, or refuse it.

        Raises:
            PermissionDenied: The principal lacks the required access. Never
                :class:`~rn_forge.web.exceptions.AuthenticationFailed` — the
                caller is authenticated; that is the 401/403 boundary.
        """
        ...


class ScopeAuthorizer:
    """An :class:`Authorizer` that evaluates a :class:`Requirement`.

    Args:
        log: Optional sink called as ``log(message, context)`` when access is
            refused. ``None`` disables logging.
    """

    def __init__(
        self, *, log: Callable[[str, Mapping[str, Any]], None] | None = None
    ) -> None:
        self._log = log

    def authorize(self, principal: Principal, *, requires: Requirement) -> None:
        """See :meth:`Authorizer.authorize`."""
        if requires.is_satisfied_by(principal):
            return
        if self._log is not None:
            self._log(
                "authorization.denied",
                {
                    "subject": principal.subject,
                    "mechanism": principal.mechanism,
                    "required": requires,
                },
            )
        raise PermissionDenied(
            "The authenticated principal lacks the required access", error_code=403
        )
