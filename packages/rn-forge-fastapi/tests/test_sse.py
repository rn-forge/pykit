"""Tests for `rn_forge.fastapi.sse`."""

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

import pytest

pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from rn_forge.fastapi.sse import (
    DEFAULT_RETRY_MS,
    sse_response,
)
from rn_forge.web import InvalidCursor, ProblemDetail, ServiceUnavailable
from sse_starlette import ServerSentEvent
from sse_starlette.sse import AppStatus


@pytest.fixture(autouse=True)
def _reset_app_status() -> Iterator[None]:
    # AppStatus is process-global; a shutdown signal in one test must not end another's stream.
    AppStatus.should_exit = False
    yield
    AppStatus.should_exit = False


def _read(events, **kwargs) -> tuple[str, bytes]:
    """Serve *events* and return the response headers' content type and the whole body."""
    app = FastAPI()

    @app.get("/stream")
    async def stream():
        return sse_response(events(), **kwargs)

    with TestClient(app) as client:
        response = client.get("/stream")
    return response.headers["content-type"], response.content


async def _two() -> AsyncIterator[ServerSentEvent]:
    yield ServerSentEvent("one", id="1")
    yield ServerSentEvent("two", event="tick")


def test_frames_reach_the_wire_after_the_retry_frame():
    content_type, body = _read(_two)

    assert content_type.startswith("text/event-stream")
    assert body == (
        b"retry: 5000\r\n\r\nid: 1\r\ndata: one\r\n\r\nevent: tick\r\ndata: two\r\n\r\n"
    )


def test_retry_defaults_to_five_seconds():
    assert DEFAULT_RETRY_MS == 5_000


def test_a_custom_retry_is_the_first_frame():
    _, body = _read(_two, retry=250)

    assert body.startswith(b"retry: 250\r\n\r\n")


def test_no_retry_frame_with_retry_none():
    _, body = _read(_two, retry=None)

    assert b"retry" not in body
    assert body.startswith(b"id: 1")


@pytest.mark.parametrize("retry", [-1, 1.5, "10", True])
def test_a_bad_retry_raises_value_error_at_call_time(retry):
    async def nothing() -> AsyncIterator[ServerSentEvent]:
        return
        yield

    with pytest.raises(ValueError, match="retry"):
        sse_response(nothing(), retry=retry)


@pytest.mark.parametrize(
    "bad",
    [
        ServerSentEvent("x", id="1\nevent: forged"),
        ServerSentEvent("x", id="1\rx"),
        ServerSentEvent("x", id="1\x00"),
        ServerSentEvent("x", event="a\nb"),
        ServerSentEvent("x", event="a\x00"),
    ],
)
def test_a_line_break_or_nul_in_id_or_event_ends_the_stream_with_an_error_frame(bad):
    async def events() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent("fine", id="1")
        yield bad
        yield ServerSentEvent("never sent")

    _, body = _read(events, retry=None)

    assert body.startswith(b"id: 1\r\ndata: fine\r\n\r\nevent: error\r\ndata: {")
    assert body.count(b"event: error") == 1
    assert b"forged" not in body
    assert b"never sent" not in body
    assert body.endswith(b"}\r\n\r\n")


def test_the_validation_failure_is_a_web_error_in_the_event_stream():
    # The wrapper is what rejects the frame, so it is observable without a server.
    from rn_forge.fastapi.sse import _frames
    from rn_forge.web import WebError, default_registry

    async def drive() -> None:
        async def source() -> AsyncIterator[ServerSentEvent]:
            yield ServerSentEvent("x", id="a\nb")

        raised: list[BaseException] = []

        registry = default_registry()
        original = registry.build

        def spy(exc: BaseException, **kw):
            raised.append(exc)
            return original(exc, **kw)

        registry.build = spy  # type: ignore[method-assign]
        frames = [f async for f in _frames(source(), None, registry, "", None)]
        assert [f.event for f in frames] == ["error"]
        assert isinstance(raised[0], WebError)

    asyncio.run(drive())


def test_an_idle_generator_gets_a_heartbeat():
    async def idle() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent("first")
        await asyncio.sleep(0.35)
        yield ServerSentEvent("last")

    _, body = _read(idle, ping=0.1, retry=None)

    assert body.startswith(b"data: first\r\n\r\n")
    assert b": ping - " in body
    assert body.endswith(b"data: last\r\n\r\n")


def test_ping_none_disables_the_heartbeat():
    async def idle() -> AsyncIterator[ServerSentEvent]:
        await asyncio.sleep(0.2)
        yield ServerSentEvent("only")

    _, body = _read(idle, ping=None, retry=None)

    assert body == b"data: only\r\n\r\n"


def test_an_escaping_exception_becomes_one_problem_frame():
    async def failing() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent("ok")
        raise ServiceUnavailable("queue is down")

    _, body = _read(failing, retry=None, instance="/jobs/7/events")

    head, _, frame = body.partition(b"data: ok\r\n\r\n")
    assert head == b""
    assert frame.startswith(b"event: error\r\ndata: ")
    assert frame.count(b"event: error") == 1
    problem = ProblemDetail.model_validate_json(
        frame.removeprefix(b"event: error\r\ndata: ").removesuffix(b"\r\n\r\n")
    )
    assert problem.status == 503
    assert problem.instance == "/jobs/7/events"
    assert "queue is down" not in problem.detail


def test_a_server_error_keeps_its_internals_off_the_wire():
    async def failing() -> AsyncIterator[ServerSentEvent]:
        raise RuntimeError("secret database password")
        yield

    _, body = _read(failing, retry=None)

    assert b"secret" not in body
    assert b'"status":500' in body.replace(b" ", b"")


def test_a_server_error_reaches_the_log_with_its_cause():
    boom = RuntimeError("secret database password")
    seen: list[tuple[str, Mapping[str, Any]]] = []

    async def failing() -> AsyncIterator[ServerSentEvent]:
        raise boom
        yield

    _read(failing, instance="/s", log=lambda event, ctx: seen.append((event, ctx)))

    assert [event for event, _ in seen] == ["problem.server_error"]
    context = seen[0][1]
    assert context["exc"] is boom
    assert context["status"] == 500
    assert context["instance"] == "/s"


def test_a_client_error_is_not_logged_as_a_server_error():
    seen: list[str] = []

    async def failing() -> AsyncIterator[ServerSentEvent]:
        raise InvalidCursor("stale")
        yield

    _read(failing, log=lambda event, _: seen.append(event))

    assert seen == []


def test_retry_zero_is_a_frame():
    _, body = _read(_two, retry=0)

    assert body.startswith(b"retry: 0\r\n")


def test_cancellation_is_not_an_error_frame():
    from rn_forge.fastapi.sse import _frames
    from rn_forge.web import default_registry

    async def drive() -> None:
        async def source() -> AsyncIterator[ServerSentEvent]:
            yield ServerSentEvent("a")
            raise asyncio.CancelledError

        frames = _frames(source(), None, default_registry(), "", None)
        assert (await anext(frames)).data == "a"
        with pytest.raises(asyncio.CancelledError):
            await anext(frames)

    asyncio.run(drive())


def test_caller_headers_override_defaults():
    async def one() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent("x")

    app = FastAPI()

    @app.get("/stream")
    async def stream():
        return sse_response(
            one(),
            headers={
                "cache-control": "no-cache",
                "x-accel-buffering": "yes",
                "x-a": "b",
            },
        )

    with TestClient(app) as client:
        response = client.get("/stream")

    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "yes"
    assert response.headers["x-a"] == "b"
