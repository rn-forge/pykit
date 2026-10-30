"""Session-wide OpenTelemetry SDK setup shared by every test in this package."""

import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

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


@pytest.fixture
def serve_jwks() -> Iterator[Callable[[list[dict[str, Any]]], str]]:
    """Serve a key set from a loopback port and return its URL; nothing leaves the machine."""
    servers: list[ThreadingHTTPServer] = []

    def serve(keys: list[dict[str, Any]]) -> str:
        payload = json.dumps({"keys": keys}).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802  # http.server hook name
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}/keys"

    yield serve
    for server in servers:
        server.shutdown()
        server.server_close()
