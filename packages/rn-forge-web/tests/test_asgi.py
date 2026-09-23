"""Tests for rn_forge.web.asgi.

The stub ASGI app below is hand-written on purpose: adding Starlette as a test
dependency would leave the boundary this whole module exists to protect
untested.
"""

import pytest
from assertpy import assert_that

from rn_forge.web.asgi import AccessLogMiddleware, Message, Receive, Scope, Send

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class StubApp:
    """Records what it saw, and emits one response with the headers it was given."""

    def __init__(self, *, response_headers: list[tuple[bytes, bytes]] | None = None):
        self.response_headers = response_headers or []
        self.seen_scopes: list[Scope] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.seen_scopes.append(scope)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": list(self.response_headers),
            }
        )
        await send({"type": "http.response.body", "body": b""})


async def _noop_receive() -> Message:
    return {"type": "http.request"}


def http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {"type": "http", "method": "GET", "path": "/", "headers": headers or []}


async def call(app, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, _noop_receive, send)
    return sent


def response_headers(sent: list[Message]) -> list[tuple[bytes, bytes]]:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["headers"]


def header_value(sent: list[Message], name: bytes) -> bytes | None:
    return next((v for k, v in response_headers(sent) if k == name), None)


async def test_a_non_http_scope_passes_through_untouched():
    stub = StubApp()
    events: list[tuple[str, dict]] = []
    scope: Scope = {"type": "lifespan"}
    await call(
        AccessLogMiddleware(
            stub, log=lambda event, ctx: events.append((event, dict(ctx)))
        ),
        scope,
    )
    assert_that(stub.seen_scopes).is_equal_to([scope])
    assert_that(events).is_empty()


async def test_the_log_sink_is_called_once_with_otel_field_names():
    events = []
    stub = StubApp()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/orders",
        "headers": [],
    }
    await call(
        AccessLogMiddleware(
            stub, log=lambda event, ctx: events.append((event, dict(ctx)))
        ),
        scope,
    )
    assert_that(events).is_length(1)
    event, fields = events[0]
    assert_that(event).is_equal_to("request.complete")
    assert_that(fields["http.request.method"]).is_equal_to("POST")
    assert_that(fields["url.path"]).is_equal_to("/orders")
    assert_that(fields["http.response.status_code"]).is_equal_to(200)
    assert_that(fields).contains_key("duration_ms")
    assert_that(fields).contains_key("trace_id")
    assert_that(fields).contains_key("span_id")


async def test_other_response_headers_are_preserved():
    stub = StubApp(response_headers=[(b"content-type", b"application/json")])
    sent = await call(AccessLogMiddleware(stub, log=lambda *a: None), http_scope())
    assert_that(header_value(sent, b"content-type")).is_equal_to(b"application/json")


async def test_the_response_body_message_is_passed_through_unmodified():
    stub = StubApp()
    sent = await call(AccessLogMiddleware(stub, log=lambda *a: None), http_scope())
    assert_that([m["type"] for m in sent]).is_equal_to(
        ["http.response.start", "http.response.body"]
    )


async def test_a_scope_with_no_headers_key_does_not_crash():
    stub = StubApp()
    sent = await call(
        AccessLogMiddleware(stub, log=lambda *a: None), {"type": "http", "path": "/"}
    )
    assert_that(response_headers(sent)).is_equal_to([])
