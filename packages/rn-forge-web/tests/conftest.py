"""Session-wide OpenTelemetry SDK setup shared by every test in this package."""

import pytest
from opentelemetry import trace
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    set_global_response_propagator,
)
from opentelemetry.sdk.trace import TracerProvider


@pytest.fixture(autouse=True, scope="session")
def _otel_sdk() -> None:
    """Configure a `TracerProvider` and response propagator once per process.

    `set_tracer_provider` can only be called once per process; a second call
    logs a warning and is ignored. Under a root-level `uv run pytest`, every
    package's conftest calls this, and the first call wins — harmless, since
    they are identical. Tests must not rely on replacing the provider between
    runs.
    """
    trace.set_tracer_provider(TracerProvider())
    set_global_response_propagator(TraceResponsePropagator())
