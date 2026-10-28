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
from rn_forge.fastapi.auth.redis import RedisCsrfStore

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
