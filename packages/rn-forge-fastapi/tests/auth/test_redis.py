"""Tests for rn_forge.fastapi.auth.redis against a fake client, and a live Redis when set."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from redis import Redis
from rn_forge.fastapi import CsrfStore
from rn_forge.fastapi import RateLimit, RateLimiter
from rn_forge.fastapi.auth.redis import RedisCsrfStore, RedisRateLimiter

pytestmark = pytest.mark.unit

REDIS_URL = "RN_FORGE_FASTAPI_REDIS_URL"
TTL = timedelta(seconds=30)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.expiry: dict[str, int] = {}

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value.encode()
        self.expiry[key] = ex

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_the_store_satisfies_the_protocol() -> None:
    assert isinstance(RedisCsrfStore(_FakeRedis()), CsrfStore)  # type: ignore[arg-type]


def test_a_token_is_one_prefixed_key_with_an_expiry() -> None:
    client = _FakeRedis()
    store = RedisCsrfStore(client, prefix="p:")  # type: ignore[arg-type]

    store.save("sid", "token", ttl=timedelta(milliseconds=1500))

    assert client.values == {"p:csrf:sid": b"token"}
    assert client.expiry == {"p:csrf:sid": 2}
    assert store.get("sid") == "token"
    store.delete("sid")
    assert store.get("sid") is None


class _FakePipeline:
    def __init__(self, client: "_FakeCounters") -> None:
        self._client = client
        self._queued: list[tuple[str, str, int | None]] = []

    def incr(self, key: str) -> None:
        self._queued.append(("incr", key, None))

    def expire(self, key: str, seconds: int) -> None:
        self._queued.append(("expire", key, seconds))

    def execute(self) -> list[int]:
        results: list[int] = []
        for command, key, seconds in self._queued:
            if command == "incr":
                self._client.counts[key] = self._client.counts.get(key, 0) + 1
                results.append(self._client.counts[key])
            else:
                assert seconds is not None
                self._client.expiry[key] = seconds
                results.append(1)
        return results


class _FakeCounters:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expiry: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


def test_the_limiter_satisfies_the_protocol() -> None:
    assert isinstance(RedisRateLimiter(_FakeCounters()), RateLimiter)  # type: ignore[arg-type]


def test_a_window_is_one_hashed_key_counted_with_incr_and_expiring_with_the_window() -> (
    None
):
    client = _FakeCounters()
    limiter = RedisRateLimiter(client, prefix="p:", clock=lambda: 125.0)  # type: ignore[arg-type]
    rate = RateLimit(2, timedelta(seconds=60))

    results = [limiter.hit("login", "ada", rate) for _ in range(3)]

    assert results == [None, None, 55]
    (key,) = client.counts
    assert key.startswith("p:rate:")
    assert "ada" not in key
    assert key.endswith(":2")
    assert client.expiry == {key: 60}
    assert client.counts[key] == 3


@pytest.fixture
def live() -> Iterator[tuple[Redis, str]]:
    if not os.environ.get(REDIS_URL):
        pytest.skip(f"{REDIS_URL} is not set")
    client: Any = Redis.from_url(os.environ[REDIS_URL])
    prefix = f"test-{uuid.uuid4().hex}:"
    yield client, prefix
    for key in client.scan_iter(match=f"{prefix}*"):
        client.delete(key)
    client.close()


def test_a_live_token_round_trips(live: tuple[Redis, str]) -> None:
    client, prefix = live
    store = RedisCsrfStore(client, prefix=prefix)

    store.save("sid", "token", ttl=TTL)

    assert store.get("sid") == "token"
    assert 0 < client.ttl(f"{prefix}csrf:sid") <= 30
    store.delete("sid")
    assert store.get("sid") is None


def test_a_live_window_counts_and_expires(live: tuple[Redis, str]) -> None:
    client, prefix = live
    limiter = RedisRateLimiter(client, prefix=prefix)
    rate = RateLimit(1, timedelta(seconds=30))

    assert limiter.hit("login", "ada", rate) is None
    assert limiter.hit("login", "ada", rate) is not None
    (key,) = client.scan_iter(match=f"{prefix}rate:*")
    assert 0 < client.ttl(key) <= 30
