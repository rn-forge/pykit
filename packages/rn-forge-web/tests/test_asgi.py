"""Tests for rn_forge.web.asgi.

The stub ASGI app below is hand-written on purpose: adding Starlette as a test
dependency would leave the boundary this whole module exists to protect
untested.
"""

import json

import pytest
from assertpy import assert_that

from rn_forge.web.asgi import BodySizeLimitMiddleware, Message, Receive, Scope, Send

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class ReadingApp:
    """Drains the request body, then answers 200."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.calls += 1
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {"type": "http", "method": "POST", "path": "/x", "headers": headers or []}


def chunked(*chunks: bytes) -> Receive:
    remaining = list(chunks)

    async def receive() -> Message:
        body = remaining.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(remaining)}

    return receive


async def call(app, scope: Scope, receive: Receive) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def status_of(sent: list[Message]) -> int:
    return next(m for m in sent if m["type"] == "http.response.start")["status"]


async def test_a_non_http_scope_passes_through_untouched():
    stub = ReadingApp()
    await call(
        BodySizeLimitMiddleware(stub, max_bytes=1),
        {"type": "lifespan"},
        chunked(b"toolong"),
    )
    assert_that(stub.calls).is_equal_to(1)


async def test_a_body_within_the_limit_reaches_the_application():
    stub = ReadingApp()
    sent = await call(
        BodySizeLimitMiddleware(stub, max_bytes=10), http_scope(), chunked(b"12345")
    )
    assert_that(status_of(sent)).is_equal_to(200)


async def test_a_declared_content_length_over_the_limit_never_reaches_the_application():
    stub = ReadingApp()
    scope = http_scope([(b"Content-Length", b"11")])
    sent = await call(BodySizeLimitMiddleware(stub, max_bytes=10), scope, chunked(b""))
    assert_that(status_of(sent)).is_equal_to(413)
    assert_that(stub.calls).is_zero()


async def test_a_streamed_body_over_the_limit_is_cut_off_with_a_problem_body():
    stub = ReadingApp()
    sent = await call(
        BodySizeLimitMiddleware(stub, max_bytes=10),
        http_scope(),
        chunked(b"123456", b"789012"),
    )
    assert_that(status_of(sent)).is_equal_to(413)
    body = json.loads(
        next(m for m in sent if m["type"] == "http.response.body")["body"]
    )
    assert_that(body["status"]).is_equal_to(413)
