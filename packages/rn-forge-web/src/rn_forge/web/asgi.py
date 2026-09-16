"""Framework-independent correlation-ID ASGI middleware and type aliases.

The middleware leaves the request-local context value bound so outer exception
handlers can read it after the application raises.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from rn_forge.web.context import (
    DEFAULT_CORRELATION_HEADER,
    new_correlation_id,
    set_correlation_id,
)

__all__ = [
    "ASGIApp",
    "CorrelationIdMiddleware",
    "Message",
    "Receive",
    "Scope",
    "Send",
]

type Scope = MutableMapping[str, Any]
"""The ASGI connection scope."""

type Message = MutableMapping[str, Any]
"""One ASGI event, in either direction."""

type Receive = Callable[[], Awaitable[Message]]
"""The ASGI receive callable."""

type Send = Callable[[Message], Awaitable[None]]
"""The ASGI send callable."""

type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
"""An ASGI application or middleware."""


def _get_header(headers: object, name: str) -> str | None:
    """Return the first value of *name* from a raw ASGI header list.

    ASGI headers are a list of ``(bytes, bytes)`` pairs and field names are
    case-insensitive, so both sides are lowercased before comparison.
    """
    if not isinstance(headers, list):
        return None
    wanted = name.lower().encode("latin-1")
    for entry in headers:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:  # pyright: ignore[reportUnknownArgumentType]
            continue
        key, value = entry  # pyright: ignore[reportUnknownVariableType]
        if isinstance(key, bytes) and key.lower() == wanted:
            if isinstance(value, bytes):
                return value.decode("latin-1")
    return None


def _set_header(message: Message, name: str, value: str) -> None:
    """Set *name* on an ``http.response.start`` message, replacing any existing value.

    Replacing rather than appending is what stops the header being emitted
    twice when an inner application already set one.
    """
    raw = message.get("headers")
    existing: list[tuple[bytes, bytes]] = []
    if isinstance(raw, list):
        for entry in raw:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(entry, (tuple, list)) and len(entry) == 2:  # pyright: ignore[reportUnknownArgumentType]
                key, val = entry  # pyright: ignore[reportUnknownVariableType]
                if isinstance(key, bytes) and isinstance(val, bytes):
                    existing.append((key, val))
    wanted = name.lower().encode("latin-1")
    kept = [(k, v) for k, v in existing if k.lower() != wanted]
    kept.append((wanted, value.encode("latin-1")))
    message["headers"] = kept


class CorrelationIdMiddleware:
    """Bind a correlation ID for the request and stamp it on the response.

    Args:
        app: The downstream ASGI application.
        header_name: The header read on the way in and written on the way out.
        generator: Produces an ID when the caller supplied none.

    Example::

        app = CorrelationIdMiddleware(app)

    A caller-supplied ID is **never replaced** — that is the whole contract.
    Non-``http`` scopes (``websocket``, ``lifespan``) pass straight through
    untouched, before anything else happens.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = DEFAULT_CORRELATION_HEADER,
        generator: Callable[[], str] = new_correlation_id,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.generator = generator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the middleware for one connection."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = (
            _get_header(scope.get("headers"), self.header_name) or self.generator()
        )
        set_correlation_id(correlation_id)

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                _set_header(message, self.header_name, correlation_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)
