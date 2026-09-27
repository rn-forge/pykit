"""Tests for rn_forge.commons.integration.resilience."""

from __future__ import annotations

import asyncio

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("purgatory")
pytest.importorskip("stamina")

from rn_forge.commons.integration.resilience import (  # noqa: E402
    CircuitOpenError,
    RateLimiter,
    ResilientAsyncHttpClient,
    parse_retry_after,
    retryable,
)


def run(coro):
    return asyncio.run(coro)


# -- parse_retry_after --------------------------------------------------


class TestParseRetryAfter:
    def test_none_returns_none(self):
        assert parse_retry_after(None) is None

    def test_empty_string_returns_none(self):
        assert parse_retry_after("") is None

    def test_delta_seconds(self):
        assert parse_retry_after("120") == 120.0

    def test_http_date(self):
        from datetime import UTC, datetime, timedelta

        future = datetime.now(UTC) + timedelta(seconds=60)
        header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        result = parse_retry_after(header)
        assert result is not None
        assert 55 <= result <= 65

    def test_garbage_returns_none(self):
        assert parse_retry_after("not a date or number") is None


# -- retryable -----------------------------------------------------------


class TestRetryable:
    def test_connect_error_is_retryable(self):
        exc = httpx.ConnectError("boom")
        assert retryable(exc) is True

    def test_timeout_is_retryable(self):
        exc = httpx.TimeoutException("boom")
        assert retryable(exc) is True

    def test_5xx_is_retryable(self):
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("err", request=request, response=response)
        assert retryable(exc) is True

    def test_4xx_is_not_retryable(self):
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(404, request=request)
        exc = httpx.HTTPStatusError("err", request=request, response=response)
        assert retryable(exc) is False

    def test_429_with_retry_after_returns_seconds(self):
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(429, headers={"Retry-After": "5"}, request=request)
        exc = httpx.HTTPStatusError("err", request=request, response=response)
        assert retryable(exc) == 5.0

    def test_other_exception_not_retryable(self):
        assert retryable(ValueError("nope")) is False


# -- RateLimiter -----------------------------------------------------------


class TestRateLimiter:
    def test_acquire_without_headers_never_waits(self):
        limiter = RateLimiter(capacity=10)
        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        run(limiter.acquire(clock=lambda: 0.0, sleep=fake_sleep))
        assert slept == []

    def test_clamped_remaining_never_optimistic(self):
        limiter = RateLimiter(capacity=100)
        limiter.update_from_headers({"X-RateLimit-Remaining": "5"})
        limiter.update_from_headers({"X-RateLimit-Remaining": "50"})
        assert limiter._remaining == 5

    def test_waits_until_reset_when_exhausted(self):
        limiter = RateLimiter(capacity=1)
        limiter.update_from_headers(
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "10"}
        )
        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        run(limiter.acquire(clock=lambda: 3.0, sleep=fake_sleep))
        assert slept == [7.0]

    def test_an_epoch_reset_is_measured_against_the_wall_clock(self):
        import time

        limiter = RateLimiter(capacity=1)
        reset = time.time() + 10
        limiter.update_from_headers(
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}
        )
        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        run(limiter.acquire(sleep=fake_sleep))
        assert len(slept) == 1 and 0 < slept[0] <= 10


# -- ResilientAsyncHttpClient ----------------------------------------------


class TestResilientAsyncHttpClient:
    def test_500_then_200_retries_and_returns_200(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(500)
            return httpx.Response(200, json={"ok": True})

        async def scenario():
            transport = httpx.MockTransport(handler)
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                wait_initial=0.001,
                wait_max=0.001,
                transport=transport,
            )
            try:
                response = await client.get("/thing")
                assert response.status_code == 200
                assert calls["n"] == 2
            finally:
                await client.close()

        run(scenario())

    def test_connect_timeout_retries_then_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("boom")

        async def scenario():
            transport = httpx.MockTransport(handler)
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                stop_after_attempt=3,
                wait_initial=0.001,
                wait_max=0.001,
                transport=transport,
            )
            try:
                with pytest.raises(httpx.ConnectTimeout):
                    await client.get("/thing")
            finally:
                await client.close()

        run(scenario())

    def test_4xx_does_not_retry(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(404)

        async def scenario():
            transport = httpx.MockTransport(handler)
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                wait_initial=0.001,
                wait_max=0.001,
                transport=transport,
            )
            try:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.get("/thing")
                assert calls["n"] == 1
            finally:
                await client.close()

        run(scenario())

    def test_breaker_opens_after_fail_max_and_stops_issuing_requests(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(500)

        async def scenario():
            transport = httpx.MockTransport(handler)
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                stop_after_attempt=1,
                fail_max=2,
                reset_timeout=60,
                wait_initial=0.001,
                wait_max=0.001,
                transport=transport,
            )
            try:
                for _ in range(2):
                    with pytest.raises(httpx.HTTPStatusError):
                        await client.get("/thing")
                calls_before = calls["n"]
                with pytest.raises(CircuitOpenError):
                    await client.get("/thing")
                assert calls["n"] == calls_before
            finally:
                await client.close()

        run(scenario())

    def test_client_errors_do_not_open_the_breaker(self):
        statuses = iter([404, 404, 200])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(next(statuses))

        async def scenario():
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                stop_after_attempt=1,
                fail_max=2,
                transport=httpx.MockTransport(handler),
            )
            try:
                for _ in range(2):
                    with pytest.raises(httpx.HTTPStatusError):
                        await client.get("/thing")
                assert (await client.get("/thing")).status_code == 200
            finally:
                await client.close()

        run(scenario())

    def test_on_state_change_invoked_on_trip(self):
        transitions = []

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        async def scenario():
            transport = httpx.MockTransport(handler)
            client = ResilientAsyncHttpClient(
                "http://test",
                name="svc",
                stop_after_attempt=1,
                fail_max=1,
                reset_timeout=60,
                wait_initial=0.001,
                wait_max=0.001,
                transport=transport,
                on_state_change=lambda name, old, new: transitions.append(
                    (name, old, new)
                ),
            )
            try:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.get("/thing")
            finally:
                await client.close()

        run(scenario())
        assert ("svc", "closed", "opened") in transitions

    def test_context_manager_closes_client(self):
        async def scenario():
            transport = httpx.MockTransport(lambda request: httpx.Response(200))
            async with ResilientAsyncHttpClient(
                "http://test", name="svc", transport=transport
            ) as client:
                await client.get("/thing")
            assert client.client.is_closed

        run(scenario())
