"""Tests for rn_forge.web.security."""

import pytest
from assertpy import assert_that

from rn_forge.web.asgi import Message, Receive, Scope, Send
from rn_forge.web.security import API_SECURITY_HEADERS, SecurityHeadersMiddleware

pytestmark = pytest.mark.unit


class StubApp:
    """Emits one response with the headers it was given."""

    def __init__(self, *, response_headers: list[tuple[bytes, bytes]] | None = None):
        self.response_headers = response_headers or []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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


def http_scope() -> Scope:
    return {"type": "http", "method": "GET", "path": "/", "headers": []}


async def call(app, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, _noop_receive, send)
    return sent


def response_headers(sent: list[Message]) -> dict[bytes, bytes]:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return dict(start["headers"])


def test_the_owasp_preset_headers_are_stamped():
    expected = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    assert_that(dict(API_SECURITY_HEADERS)).is_equal_to(expected)


def test_hsts_is_not_in_the_default_preset():
    assert_that(API_SECURITY_HEADERS).does_not_contain_key("Strict-Transport-Security")


@pytest.mark.asyncio
async def test_every_preset_header_is_stamped_on_a_bare_response():
    sent = await call(SecurityHeadersMiddleware(StubApp()), http_scope())
    headers = response_headers(sent)
    for name, value in API_SECURITY_HEADERS.items():
        assert_that(headers[name.encode()]).is_equal_to(value.encode())


@pytest.mark.asyncio
async def test_a_downstream_cache_control_wins():
    stub = StubApp(response_headers=[(b"cache-control", b"public, max-age=3600")])
    sent = await call(SecurityHeadersMiddleware(stub), http_scope())
    assert_that(response_headers(sent)[b"cache-control"]).is_equal_to(
        b"public, max-age=3600"
    )


@pytest.mark.asyncio
async def test_the_check_is_case_insensitive():
    stub = StubApp(response_headers=[(b"Cache-Control", b"public")])
    sent = await call(SecurityHeadersMiddleware(stub), http_scope())
    values = [
        v for k, v in response_headers(sent).items() if k.lower() == b"cache-control"
    ]
    assert_that(values).is_equal_to([b"public"])


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_type", ["websocket", "lifespan"])
async def test_a_non_http_scope_passes_through_untouched(scope_type):
    stub = StubApp()
    await call(SecurityHeadersMiddleware(stub), {"type": scope_type})
