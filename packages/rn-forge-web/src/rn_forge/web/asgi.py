"""Framework-independent ASGI middleware and type aliases.

The middleware wraps any ASGI application — FastAPI, Starlette, or Django
served over ASGI.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from rn_forge.web.exceptions import ContentTooLarge
from rn_forge.web.problem import BLANK_TYPE, PROBLEM_MEDIA_TYPE, CONTENT_TOO_LARGE
from rn_forge.web.tracing import TRACE_ID_KEY, current_trace_id

__all__ = [
    "ASGIApp",
    "BodySizeLimitMiddleware",
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


class BodySizeLimitMiddleware:
    """Reject a request body over *max_bytes* with RFC 9110 §15.5.14's 413.

    Rejects a declared ``Content-Length`` over the limit before the downstream
    application runs at all. A streamed body with no (or an understated)
    ``Content-Length`` is checked as it arrives; :class:`ContentTooLarge` is
    raised out of the wrapped ``receive`` so the downstream application's read
    aborts, and this middleware sends the 413 itself — unless the downstream
    application already started its own response, in which case nothing more
    can be done and the partial response stands.

    Args:
        app: The downstream ASGI application.
        max_bytes: The largest body this middleware admits.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the middleware for one connection."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        declared = _get_header(scope.get("headers"), "content-length")
        if (
            declared is not None
            and declared.isdigit()
            and int(declared) > self.max_bytes
        ):
            await _send_413(send, str(scope.get("path", "")))
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        received = 0

        async def receive_wrapper() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise ContentTooLarge("Request body exceeds the configured limit")
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except ContentTooLarge:
            if started:
                raise
            await _send_413(send, str(scope.get("path", "")))


async def _send_413(send: Send, path: str) -> None:
    """Send a minimal, framework-free 413 problem response."""
    body = json.dumps(
        {
            "type": BLANK_TYPE,
            "title": CONTENT_TOO_LARGE.title,
            "status": CONTENT_TOO_LARGE.status,
            "detail": "Request body exceeds the configured limit",
            "instance": path,
            TRACE_ID_KEY: current_trace_id(),
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": CONTENT_TOO_LARGE.status,
            "headers": [
                (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
