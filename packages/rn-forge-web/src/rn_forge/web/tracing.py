"""W3C Trace Context: the current trace and span ids.

The current trace is read from OpenTelemetry's active span. This module never
configures a ``TracerProvider`` or an exporter — those are the application's
job (or ``opentelemetry-instrument``'s), per OpenTelemetry's own library
guidance.
"""

from __future__ import annotations

from typing import Final

from opentelemetry import trace

__all__ = [
    "EXPOSED_HEADERS",
    "TRACE_ID_KEY",
    "current_span_id",
    "current_trace_id",
]

TRACE_ID_KEY: Final = "traceId"
"""The problem-body extension member that carries the current trace id."""

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
