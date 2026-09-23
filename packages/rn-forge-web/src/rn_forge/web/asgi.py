"""Framework-independent correlation-ID ASGI middleware and type aliases.

The middleware wraps any ASGI application — FastAPI, Starlette, or Django
served over ASGI. It leaves the request-local context value bound so outer
exception handlers can read it after the application raises.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from rn_forge.web.context import (
    CORRELATION_ID_KEY,
    DEFAULT_CORRELATION_HEADER,
    get_correlation_id,
    is_valid_correlation_id,
    new_correlation_id,
    request_log_fields,
    resolve_correlation_id,
    set_correlation_id,
)
from rn_forge.web.exceptions import ContentTooLarge
from rn_forge.web.problem import BLANK_TYPE, PROBLEM_MEDIA_TYPE, CONTENT_TOO_LARGE

__all__ = [
    "ASGIApp",
    "BodySizeLimitMiddleware",
    "CorrelationIdMiddleware",
    "Log",
    "Message",
    "Receive",
    "Scope",
    "Send",
]

type Log = Callable[[str, Mapping[str, Any]], None]
"""A sink for a structured log event: an event name and its fields."""

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
        generator: Produces an ID when the caller supplied none, or supplied
            one that *validator* rejects.
        validator: Returns whether a caller-supplied ID is well-formed.
        log: A sink for a ``request.complete`` event
            (:func:`~rn_forge.web.context.request_log_fields`), emitted once
            per request. ``None`` (the default) logs nothing.

    Example::

        app = CorrelationIdMiddleware(app)

    A caller-supplied ID is **never replaced when it is well-formed** — that
    is the whole contract. A malformed one (by default: empty, over
    :data:`~rn_forge.web.context.MAX_CORRELATION_ID_LENGTH` characters, or
    containing anything outside ``[A-Za-z0-9._:-]``) is replaced by
    *generator*, never sanitized: rewriting a caller's ID would produce one
    that matches neither end's logs. Pass ``validator=lambda _: True`` to
    restore the old always-echo behavior. Non-``http`` scopes (``websocket``,
    ``lifespan``) pass straight through untouched, before anything else
    happens.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = DEFAULT_CORRELATION_HEADER,
        generator: Callable[[], str] = new_correlation_id,
        validator: Callable[[str], bool] = is_valid_correlation_id,
        log: Log | None = None,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.generator = generator
        self.validator = validator
        self.log = log

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the middleware for one connection."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        inbound = _get_header(scope.get("headers"), self.header_name)
        correlation_id = resolve_correlation_id(
            inbound, validator=self.validator, generator=self.generator
        )
        set_correlation_id(correlation_id)

        started = time.perf_counter()
        status: list[int] = []

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                _set_header(message, self.header_name, correlation_id)
                raw_status = message.get("status")
                if isinstance(raw_status, int):
                    status.append(raw_status)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if self.log is not None:
            self.log(
                "request.complete",
                request_log_fields(
                    method=str(scope.get("method", "")),
                    path=str(scope.get("path", "")),
                    status=status[-1] if status else 0,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    correlation_id=correlation_id,
                ),
            )


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
            CORRELATION_ID_KEY: get_correlation_id(),
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
