"""Server-sent events over FastAPI.

Requires the ``sse`` extra. Not imported by :mod:`rn_forge.fastapi`.

Importing this module imports ``sse_starlette``, which replaces
``uvicorn.Server.handle_exit`` for the whole process so that open streams are
drained on shutdown (``sse_starlette.sse.AppStatus``).

:func:`sse_response` returns an ``EventSourceResponse``; the media type, the
``cache-control`` and ``x-accel-buffering`` headers, the heartbeat, disconnect
handling and graceful shutdown are its. This module adds validation of frame
fields, a terminal ``error`` frame, and a ``retry`` frame. It does not read
``Last-Event-ID``: the route does, and passes it to the event source.
"""

import json
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import Final

from rn_forge.fastapi.problem import Log
from rn_forge.web import (
    ProblemRegistry,
    WebError,
    current_trace_id,
    default_registry,
    render_problem,
)
from sse_starlette import EventSourceResponse, ServerSentEvent

__all__ = ["DEFAULT_PING_SECONDS", "DEFAULT_RETRY_MS", "sse_response"]

DEFAULT_PING_SECONDS: Final = 15.0
"""Seconds between heartbeat comments on an idle stream."""

DEFAULT_RETRY_MS: Final = 5_000
"""Milliseconds a client waits before reconnecting a dropped stream."""

_ERROR_EVENT: Final = "error"
_FORBIDDEN: Final = "\r\n\x00"

# No `rn_forge.web.conformance` case: both framework drivers run every case with
# no skips, and `rn-forge-django` has no SSE adapter.


def sse_response(
    events: AsyncIterable[ServerSentEvent],
    *,
    ping: float | None = DEFAULT_PING_SECONDS,
    retry: int | None = DEFAULT_RETRY_MS,
    registry: ProblemRegistry | None = None,
    instance: str = "",
    headers: Mapping[str, str] | None = None,
    log: Log | None = None,
) -> EventSourceResponse:
    """Stream *events* as ``text/event-stream``.

    Args:
        events: The frames to send, in order.
        ping: Seconds between heartbeat comments while the stream is idle.
            ``None`` or ``0`` disables the heartbeat.
        retry: Milliseconds a browser ``EventSource`` waits before reconnecting.
            Sent as the first frame; ``None`` sends no such frame.
        registry: Maps an exception escaping *events* to its problem. Defaults
            to :func:`~rn_forge.web.default_registry`.
        instance: The problem's ``instance`` member.
        headers: Response headers. They are applied last, so each replaces a
            default of the same name.
        log: Called as ``log("problem.server_error", context)`` for a 5xx
            problem, with the exception under ``"exc"``, as
            :func:`~rn_forge.fastapi.problem.register_problem_handlers` does.

    Returns:
        The response. Each frame of *events* is sent as given, except that an
        ``id`` or ``event`` containing ``\\r``, ``\\n`` or ``\\x00`` is rejected
        with :class:`~rn_forge.web.WebError`. An exception escaping *events*,
        that one included, ends the stream with a single frame whose ``event``
        is ``error`` and whose ``data`` is the problem as JSON, as
        ``registry`` renders it. Cancellation and client disconnect are not
        errors and send nothing.

    Raises:
        ValueError: *retry* is not a non-negative integer, or *ping* is negative.
    """
    if retry is not None and (type(retry) is not int or retry < 0):
        raise ValueError(f"retry must be a non-negative integer, got {retry!r}")
    response = EventSourceResponse(
        _frames(events, retry, registry or default_registry(), instance, log),
        ping=0 if ping is None else ping,
    )
    # Applied after construction: the response overwrites some defaults itself.
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


async def _frames(
    events: AsyncIterable[ServerSentEvent],
    retry: int | None,
    registry: ProblemRegistry,
    instance: str,
    log: Log | None,
) -> AsyncIterator[ServerSentEvent]:
    if retry is not None:
        yield ServerSentEvent(retry=retry)
    source = aiter(events)
    try:
        async for event in source:
            _check(event.id, "id")
            _check(event.event, "event")
            yield event
    except Exception as exc:  # noqa: BLE001  # CancelledError is not an Exception
        rendered = render_problem(registry, exc, instance=instance)
        if rendered.status >= 500 and log is not None:
            log(
                "problem.server_error",
                {
                    "exc": exc,
                    "status": rendered.status,
                    "instance": rendered.problem.instance,
                    "trace_id": current_trace_id(),
                },
            )
        yield ServerSentEvent(event=_ERROR_EVENT, data=json.dumps(rendered.body))
    finally:
        # Closing this generator does not close the source it is iterating.
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            await aclose()


def _check(value: str | None, field: str) -> None:
    if value is not None and any(char in value for char in _FORBIDDEN):
        raise WebError(f"SSE {field} contains a line break or NUL")
