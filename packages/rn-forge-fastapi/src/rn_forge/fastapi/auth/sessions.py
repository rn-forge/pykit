"""The login session, kept in an ``rn-forge-auth`` :class:`~rn_forge.auth.SessionStore`.

The session ID travels in the ``__Host-session`` cookie. Every store call is
synchronous; async code runs these methods in the thread pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from fastapi import Request, Response
from rn_forge.auth import (
    AuthorizationContext,
    AuthorizationContextProvider,
    SessionInfo,
    SessionStore,
)

__all__ = ["SESSION_COOKIE", "ActiveSession", "Sessions"]

SESSION_COOKIE: Final = "__Host-session"
"""The cookie that carries the session ID."""


@dataclass(frozen=True)
class ActiveSession:
    """A session with its account's current authorization context.

    Attributes:
        info: The session's content.
        context: The account's authorization context.
    """

    info: SessionInfo
    context: AuthorizationContext


class Sessions:
    """Starts, reads and ends login sessions.

    Args:
        store: Holds the sessions.
        contexts: Supplies the account's current context.
        idle_timeout: How long a session may sit unused.
        absolute_timeout: How long a session lives whatever its use.
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        contexts: AuthorizationContextProvider,
        idle_timeout: timedelta,
        absolute_timeout: timedelta,
    ) -> None:
        self._store = store
        self._contexts = contexts
        self._idle = idle_timeout
        self.absolute_timeout = absolute_timeout

    @staticmethod
    def now() -> datetime:
        """The current time, aware."""
        return datetime.now(UTC)

    @staticmethod
    def session_id(request: Request) -> str | None:
        """The session ID the request's cookie carries, if any."""
        return request.cookies.get(SESSION_COOKIE)

    def start(self, info: SessionInfo, *, previous: str | None = None) -> str:
        """Store *info* under a new session ID and delete the session *previous*.

        Returns:
            The new session ID.
        """
        if previous is not None:
            self._store.delete(previous)
        return self._store.create(info, idle_ttl=self._idle)

    def read(self, session_id: str | None) -> ActiveSession | None:
        """Return the session with ID *session_id*, or ``None`` when there is none.

        Reading does not extend the session.
        """
        if not session_id:
            return None
        info = self._store.get(session_id)
        if info is None:
            return None
        return ActiveSession(info, self._contexts.resolve(info.account_id))

    def end(self, session_id: str | None) -> None:
        """Delete the session with ID *session_id*, if there is one."""
        if session_id:
            self._store.delete(session_id)

    def set_cookie(
        self, response: Response, session_id: str, info: SessionInfo
    ) -> None:
        """Set the session cookie on *response*."""
        remaining = min(self._idle, info.expires_at - self.now())
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            max_age=max(1, int(remaining.total_seconds())),
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )

    @staticmethod
    def clear_cookie(response: Response) -> None:
        """Delete the session cookie on *response*."""
        response.delete_cookie(
            SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
        )
