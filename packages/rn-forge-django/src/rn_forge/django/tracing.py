"""OpenTelemetry instrumentation for Django.

**Requires the ``otel`` extra.** Not re-exported from any facade; call
:func:`instrument` once, before Django loads.
"""

from __future__ import annotations

from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    get_global_response_propagator,
    set_global_response_propagator,  # pyright: ignore[reportUnknownVariableType]
)

__all__ = ["instrument"]


def instrument() -> None:
    """Instrument Django with OpenTelemetry, and set a response propagator.

    Call this once, from ``wsgi.py``/``asgi.py`` and ``manage.py``, before
    Django loads — the native pattern: `DjangoInstrumentor` inserts its own
    middleware into ``MIDDLEWARE`` at position 0 itself, so it wraps
    everything downstream, including the DRF exception handler.

    Idempotent: `DjangoInstrumentor().instrument()` is a no-op on a second
    call. A `TraceResponsePropagator` is set as the global response
    propagator only when nothing else has — process-global state, set only
    when nobody else set it.
    """
    DjangoInstrumentor().instrument()
    if get_global_response_propagator() is None:
        set_global_response_propagator(TraceResponsePropagator())
