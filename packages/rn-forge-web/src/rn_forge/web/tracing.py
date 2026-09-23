"""W3C Trace Context propagation and access-log fields.

The current trace is read from OpenTelemetry's active span. This module never
configures a ``TracerProvider`` or an exporter — those are the application's
job (or ``opentelemetry-instrument``'s), per OpenTelemetry's own library
guidance.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Final

from opentelemetry import trace

__all__ = [
    "EXPOSED_HEADERS",
    "SPAN_ID_KEY",
    "TRACE_ID_KEY",
    "current_span_id",
    "current_trace_id",
    "request_log_fields",
    "trace_log_processor",
]

TRACE_ID_KEY: Final = "trace_id"
"""The key :func:`trace_log_processor` writes, and the problem-body extension name."""

SPAN_ID_KEY: Final = "span_id"
"""The key :func:`trace_log_processor` writes for the current span id."""

EXPOSED_HEADERS: Final[tuple[str, ...]] = (
    "ETag",
    "Link",
    "Location",
    "Retry-After",
    "Deprecation",
    "Sunset",
)
"""Response headers this kit emits that a browser can read only when a CORS
policy names them in ``Access-Control-Expose-Headers``.

An application's own CORS configuration does not know what the kit emits; a
CORS binding passes this list so the kit's own concurrency, discovery and
retry contracts survive a browser client. ``traceresponse`` is not listed
here: the OpenTelemetry response propagator exposes it itself.
"""


def current_trace_id() -> str | None:
    """Return the current span's trace id, or ``None`` when no span is recording."""
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def current_span_id() -> str | None:
    """Return the current span's id, or ``None`` when no span is recording."""
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.span_id, "016x") if ctx.is_valid else None


def request_log_fields(
    *,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
) -> dict[str, Any]:
    """Return one access-log event's fields.

    Method, path and status follow the OpenTelemetry HTTP semantic
    conventions' attribute names, so a log pipeline and a trace span agree on
    what to call them.

    Args:
        method: The request method.
        path: The request path.
        status: The response status code.
        duration_ms: How long the request took, in milliseconds.

    Returns:
        ``http.request.method``, ``url.path``, ``http.response.status_code``,
        ``duration_ms``, ``trace_id`` and ``span_id`` (either may be ``None``).
    """
    return {
        "http.request.method": method,
        "url.path": path,
        "http.response.status_code": status,
        "duration_ms": duration_ms,
        TRACE_ID_KEY: current_trace_id(),
        SPAN_ID_KEY: current_span_id(),
    }


def trace_log_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject the current span's trace and span ids into a structlog event dict.

    Usable directly as a structlog processor without importing structlog.

    Args:
        logger: The bound logger. Unused; part of the processor signature.
        method_name: The log method's name. Unused; part of the signature.
        event_dict: The event dictionary, mutated in place and returned.

    Returns:
        *event_dict*, with ``trace_id`` and ``span_id`` set when a span is
        recording and left untouched when none is.
    """
    del logger, method_name
    trace_id = current_trace_id()
    if trace_id is not None:
        event_dict[TRACE_ID_KEY] = trace_id
        event_dict[SPAN_ID_KEY] = current_span_id()
    return event_dict
