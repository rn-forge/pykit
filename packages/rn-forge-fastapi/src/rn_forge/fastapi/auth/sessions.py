"""The login session, kept in an ``rn-forge-auth`` :class:`~rn_forge.auth.SessionStore`.

The session ID travels in the ``__Host-session`` cookie. Every store call is
synchronous; :class:`Sessions` methods are blocking and async code runs them
in the thread pool. :class:`SessionMiddleware` resolves the session once per
request and keeps its cookie current.

``GET`` requests to the paths in ``untouched_paths`` read the session without
extending it; every other request moves the idle expiry forward.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from fastapi import Request, Response
from fastapi.concurrency import run_in_threadpool
from rn_forge.auth import (
    AuthorizationContext,
    AuthorizationContextProvider,
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    ReplayStore,
    SessionInfo,
    SessionStore,
    TransactionStore,
)
from starlette.datastructures import MutableHeaders

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "SESSION_COOKIE",
    "ActiveSession",
    "SessionMiddleware",
    "Sessions",
    "active_session",
    "refuse_in_memory",
    "rotate_session",
]

_STATE_KEY: Final = "rn_forge_session"

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


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Sessions:
    """Starts, reads, rotates and ends login sessions.

    Args:
        store: Holds the sessions.
        contexts: Supplies the account's current context for the checks.
        replay: Says which ``(issuer, sid)`` pairs are revoked.
        idle_timeout: How long a session may sit unused.
        absolute_timeout: How long a session lives whatever its use.
        debug: Allow in-memory stores.
        clock: Returns the current time, aware.

    Raises:
        RuntimeError: *debug* is false and *store* or *replay* is held in
            process memory.
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        contexts: AuthorizationContextProvider,
        replay: ReplayStore,
        idle_timeout: timedelta,
        absolute_timeout: timedelta,
        debug: bool = False,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not debug:
            refuse_in_memory(session_store=store, replay_store=replay)
        self._store = store
        self._contexts = contexts
        self._replay = replay
        self._idle = idle_timeout
        self.absolute_timeout = absolute_timeout
        self._clock = clock

    def now(self) -> datetime:
        """The current time, aware."""
        return self._clock()

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

    def read(
        self, session_id: str | None, *, touch: bool = True
    ) -> ActiveSession | None:
        """Return the session with ID *session_id*, or ``None`` when there is none.

        A session past its absolute timeout, whose recorded version differs
        from its account's, whose account is inactive, or whose ``session_ref``
        is revoked, is deleted and read as absent.

        Args:
            session_id: The session ID from the cookie.
            touch: Move the idle expiry forward. ``False`` reads without
                extending the session.
        """
        if not session_id:
            return None
        info = self._store.get(session_id)
        if info is None:
            return None
        context = self._contexts.resolve(info.account_id)
        if (
            self.now() >= info.expires_at
            or not context.active
            or context.session_version != info.session_version
            or (
                info.session_ref is not None
                and self._replay.is_sid_revoked(info.issuer, info.session_ref)
            )
        ):
            self._store.delete(session_id)
            return None
        # A touch that finds the session gone means a concurrent logout won.
        if touch and not self._store.touch(session_id, idle_ttl=self._idle):
            return None
        return ActiveSession(info, context)

    def rotate(self, session_id: str) -> str | None:
        """Move the session to a new ID; the old ID is unreadable afterwards.

        Returns:
            The new session ID, or ``None`` when the session is absent.
        """
        return self._store.rotate(session_id, idle_ttl=self._idle)

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


def refuse_in_memory(
    *,
    session_store: SessionStore | None = None,
    replay_store: ReplayStore | None = None,
    transaction_store: TransactionStore | None = None,
) -> None:
    """Refuse stores held in process memory, which processes do not share.

    Raises:
        RuntimeError: A given store is an in-memory store.
    """
    for name, store, kind in (
        ("sessions", session_store, InMemorySessionStore),
        ("replay", replay_store, InMemoryReplayStore),
        ("transactions", transaction_store, InMemoryTransactionStore),
    ):
        if isinstance(store, kind):
            raise RuntimeError(  # noqa: TRY004  # a configuration error
                f"The {name} store is held in process memory, which is not shared "
                "between processes and loses revocations; use the Redis store "
                "(or set debug=True for development)"
            )


@dataclass
class _Held:
    """What the middleware resolved for one request."""

    sessions: Sessions
    session_id: str | None
    active: ActiveSession | None
    cookie_sent: bool
    touched: bool
    rotated: bool = False


def _held(request: Request) -> _Held | None:
    state: dict[str, Any] = request.scope.get("state", {})
    held = state.get(_STATE_KEY)
    return held if isinstance(held, _Held) else None


def request_session(request: Request) -> tuple[str | None, ActiveSession | None] | None:
    """The ``(session_id, session)`` the middleware resolved, or ``None`` without it."""
    held = _held(request)
    return None if held is None else (held.session_id, held.active)


def active_session(request: Request) -> ActiveSession | None:
    """The request's session as :class:`SessionMiddleware` resolved it.

    Returns:
        The session, or ``None`` when the request has none.

    Raises:
        RuntimeError: :class:`SessionMiddleware` is not installed.
    """
    resolved = request_session(request)
    if resolved is None:
        raise RuntimeError("SessionMiddleware is not installed")
    return resolved[1]


async def rotate_session(request: Request) -> None:
    """Give the request's session a new ID and keep its content.

    Call it after a change of the account's privileges, so a session ID that
    was seen before the change is useless afterwards. The middleware sets the
    new cookie on the response. A request with no session is left alone.

    Raises:
        RuntimeError: :class:`SessionMiddleware` is not installed.
    """
    held = _held(request)
    if held is None:
        raise RuntimeError("SessionMiddleware is not installed")
    if held.session_id is None or held.active is None:
        return
    new_id = await run_in_threadpool(held.sessions.rotate, held.session_id)
    held.session_id = new_id
    held.rotated = True
    if new_id is None:
        held.active = None


class SessionMiddleware:
    """Resolve the login session once per request and keep its cookie current.

    The session is available through :func:`active_session`. Every request
    except a ``GET`` to *untouched_paths* extends the idle expiry and refreshes
    the cookie's ``Max-Age``; a request whose cookie names no valid session
    gets the cookie cleared, unless its response sets the cookie itself.

    Args:
        app: The wrapped ASGI application.
        sessions: Reads and extends the sessions.
        untouched_paths: Paths whose ``GET`` requests do not extend the session.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        sessions: Sessions,
        untouched_paths: Collection[str] = ("/auth/session",),
    ) -> None:
        self.app = app
        self._sessions = sessions
        self._untouched = frozenset(untouched_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        session_id = Sessions.session_id(Request(scope))
        touch = not (scope["method"] == "GET" and scope["path"] in self._untouched)
        active = await run_in_threadpool(self._sessions.read, session_id, touch=touch)
        held = _Held(
            self._sessions,
            session_id if active else None,
            active,
            cookie_sent=bool(session_id),
            touched=touch,
        )
        state: MutableMapping[str, Any] = scope.setdefault("state", {})
        state[_STATE_KEY] = held

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._set_cookie(held, MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    def _set_cookie(self, held: _Held, headers: MutableHeaders) -> None:
        prefix = f"{SESSION_COOKIE}="
        if any(value.startswith(prefix) for value in headers.getlist("set-cookie")):
            return
        carrier = Response()
        if (
            held.active is not None
            and held.session_id
            and (held.touched or held.rotated)
        ):
            self._sessions.set_cookie(carrier, held.session_id, held.active.info)
        elif held.active is None and (held.cookie_sent or held.rotated):
            self._sessions.clear_cookie(carrier)
        for name, value in carrier.raw_headers:
            if name == b"set-cookie":
                headers.append("set-cookie", value.decode("latin-1"))
