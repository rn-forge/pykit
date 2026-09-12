"""Tests for rn_forge.web.asgi.

The stub ASGI app below is hand-written on purpose: adding Starlette as a test
dependency would leave the boundary this whole module exists to protect
untested.
"""

import pytest
from assertpy import assert_that

from rn_forge.web.asgi import CorrelationIdMiddleware, Message, Receive, Scope, Send
from rn_forge.web.context import correlation_id_var, get_correlation_id

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class StubApp:
    """Records what it saw, and emits one response with the headers it was given."""

    def __init__(self, *, response_headers: list[tuple[bytes, bytes]] | None = None):
        self.response_headers = response_headers or []
        self.seen_scopes: list[Scope] = []
        self.seen_correlation_ids: list[str | None] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.seen_scopes.append(scope)
        self.seen_correlation_ids.append(get_correlation_id())
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


@pytest.fixture(autouse=True)
def _clean_contextvar():
    token = correlation_id_var.set(None)
    yield
    correlation_id_var.reset(token)


async def test_an_inbound_id_is_preserved_through_to_the_response():
    """Never replace a caller-supplied ID — that is the whole contract."""
    stub = StubApp()
    sent = await call(
        CorrelationIdMiddleware(stub),
        http_scope([(b"x-correlation-id", b"abc123")]),
    )
    assert_that(header_value(sent, b"x-correlation-id")).is_equal_to(b"abc123")
    assert_that(stub.seen_correlation_ids).is_equal_to(["abc123"])


async def test_an_absent_id_is_generated_and_stamped():
    stub = StubApp()
    sent = await call(CorrelationIdMiddleware(stub), http_scope())
    stamped = header_value(sent, b"x-correlation-id")
    assert_that(stamped).is_not_none()
    assert_that(stub.seen_correlation_ids[0]).is_equal_to(stamped.decode())


async def test_the_header_is_matched_case_insensitively():
    stub = StubApp()
    await call(
        CorrelationIdMiddleware(stub), http_scope([(b"X-CoRrElAtIoN-Id", b"abc123")])
    )
    assert_that(stub.seen_correlation_ids).is_equal_to(["abc123"])


async def test_the_context_var_is_readable_from_inside_the_wrapped_app():
    stub = StubApp()
    await call(CorrelationIdMiddleware(stub), http_scope())
    assert_that(stub.seen_correlation_ids[0]).is_not_none()


@pytest.mark.parametrize("scope_type", ["websocket", "lifespan"])
async def test_a_non_http_scope_passes_through_untouched(scope_type):
    stub = StubApp()
    scope: Scope = {"type": scope_type}
    await call(CorrelationIdMiddleware(stub), scope)
    assert_that(stub.seen_scopes).is_equal_to([scope])
    assert_that(get_correlation_id()).is_none()


async def test_a_custom_header_name_is_honoured():
    stub = StubApp()
    sent = await call(
        CorrelationIdMiddleware(stub, header_name="X-Request-ID"),
        http_scope([(b"x-request-id", b"abc123")]),
    )
    assert_that(header_value(sent, b"x-request-id")).is_equal_to(b"abc123")
    assert_that(stub.seen_correlation_ids).is_equal_to(["abc123"])


async def test_a_custom_generator_is_honoured():
    stub = StubApp()
    sent = await call(
        CorrelationIdMiddleware(stub, generator=lambda: "fixed"), http_scope()
    )
    assert_that(header_value(sent, b"x-correlation-id")).is_equal_to(b"fixed")


async def test_the_header_is_not_duplicated_when_the_app_already_set_one():
    stub = StubApp(response_headers=[(b"x-correlation-id", b"inner")])
    sent = await call(CorrelationIdMiddleware(stub), http_scope())
    matching = [k for k, _ in response_headers(sent) if k == b"x-correlation-id"]
    assert_that(matching).is_length(1)


async def test_other_response_headers_are_preserved():
    stub = StubApp(response_headers=[(b"content-type", b"application/json")])
    sent = await call(CorrelationIdMiddleware(stub), http_scope())
    assert_that(header_value(sent, b"content-type")).is_equal_to(b"application/json")


async def test_the_response_body_message_is_passed_through_unmodified():
    stub = StubApp()
    sent = await call(CorrelationIdMiddleware(stub), http_scope())
    assert_that([m["type"] for m in sent]).is_equal_to(
        ["http.response.start", "http.response.body"]
    )


async def test_a_scope_with_no_headers_key_does_not_crash():
    stub = StubApp()
    sent = await call(CorrelationIdMiddleware(stub), {"type": "http", "path": "/"})
    assert_that(header_value(sent, b"x-correlation-id")).is_not_none()


async def test_the_context_var_survives_after_the_app_returns():
    """The no-reset design: an outer error handler must still see the value."""
    stub = StubApp()
    await call(CorrelationIdMiddleware(stub, generator=lambda: "fixed"), http_scope())
    assert_that(get_correlation_id()).is_equal_to("fixed")
