"""Tests for rn_forge.auth.redis; skipped without ``RN_FORGE_AUTH_REDIS_URL``."""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.auth import (
    AuthorizationVersions,
    LoginTransaction,
    ReplayStore,
    SessionInfo,
    SessionStore,
    TransactionStore,
)

REDIS_URL = "RN_FORGE_AUTH_REDIS_URL"

if not os.environ.get(REDIS_URL):
    pytest.skip(f"{REDIS_URL} is not set", allow_module_level=True)

from redis import Redis  # noqa: E402
from rn_forge.auth.redis import (  # noqa: E402
    RedisAuthorizationVersions,
    RedisReplayStore,
    RedisSessionStore,
    RedisTransactionStore,
)

pytestmark = pytest.mark.unit

TTL = timedelta(seconds=30)
IDLE = timedelta(minutes=30)


@pytest.fixture
def client() -> Iterator[Redis]:
    connection = Redis.from_url(os.environ[REDIS_URL])
    yield connection
    connection.close()


@pytest.fixture
def prefix(client: Redis) -> Iterator[str]:
    value = f"test-{uuid.uuid4().hex}:"
    yield value
    for key in client.scan_iter(match=f"{value}*"):
        client.delete(key)


def _transaction() -> LoginTransaction:
    return LoginTransaction(
        id="tx1",
        provider="idp",
        return_to="/home",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        state="s",
        nonce="n",
        code_verifier="v",
        extra={"k": "v"},
    )


def _session(expires_in: timedelta = timedelta(hours=12)) -> SessionInfo:
    now = datetime.now(UTC)
    return SessionInfo(
        account_id="acct",
        session_version=3,
        provider="idp",
        issuer="https://iss",
        external_subject="sub",
        created_at=now,
        expires_at=now + expires_in,
        auth_time=now,
        amr=frozenset({"pwd", "mfa"}),
        session_ref="sid1",
        id_token="tok",
    )


def test_the_stores_satisfy_the_protocols(client: Redis, prefix: str) -> None:
    assert isinstance(RedisTransactionStore(client, prefix=prefix), TransactionStore)
    assert isinstance(RedisSessionStore(client, prefix=prefix), SessionStore)
    assert isinstance(RedisReplayStore(client, prefix=prefix), ReplayStore)
    assert isinstance(
        RedisAuthorizationVersions(client, prefix=prefix), AuthorizationVersions
    )


def test_a_transaction_round_trips_and_is_consumed_once(
    client: Redis, prefix: str
) -> None:
    store = RedisTransactionStore(client, prefix=prefix)
    store.save(_transaction(), ttl=TTL)
    assert store.consume("tx1") == _transaction()
    assert store.consume("tx1") is None


def test_50_concurrent_consumes_of_a_transaction_have_one_winner(
    client: Redis, prefix: str
) -> None:
    store = RedisTransactionStore(client, prefix=prefix)
    store.save(_transaction(), ttl=TTL)
    barrier = threading.Barrier(50)

    def attempt() -> LoginTransaction | None:
        barrier.wait()
        return store.consume("tx1")

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = [f.result() for f in [pool.submit(attempt) for _ in range(50)]]
    assert len([r for r in results if r is not None]) == 1


def test_a_transaction_expires(client: Redis, prefix: str) -> None:
    store = RedisTransactionStore(client, prefix=prefix)
    store.save(_transaction(), ttl=timedelta(seconds=1))
    time.sleep(1.2)
    assert store.consume("tx1") is None


def test_record_once_is_true_only_the_first_time(client: Redis, prefix: str) -> None:
    store = RedisReplayStore(client, prefix=prefix)
    assert store.record_once("jti", ttl=TTL) is True
    assert store.record_once("jti", ttl=TTL) is False


def test_a_revoked_sid_expires(client: Redis, prefix: str) -> None:
    store = RedisReplayStore(client, prefix=prefix)
    assert store.is_sid_revoked("iss", "s1") is False
    store.revoke_sid("iss", "s1", ttl=timedelta(seconds=1))
    assert store.is_sid_revoked("iss", "s1") is True
    assert store.is_sid_revoked("iss:x", "s1") is False
    time.sleep(1.2)
    assert store.is_sid_revoked("iss", "s1") is False


def test_a_version_bump_reaches_another_client(client: Redis, prefix: str) -> None:
    first = RedisAuthorizationVersions(client, prefix=prefix)
    other = Redis.from_url(os.environ[REDIS_URL])
    try:
        second = RedisAuthorizationVersions(other, prefix=prefix)
        assert second.current("a1") == (0, 0)
        first.bump("a1")
        assert second.current("a1") == (1, 0)
        assert second.current("a2") == (0, 0)
        first.bump_all()
        assert second.current("a1") == (1, 1)
    finally:
        other.close()


def test_a_session_round_trips_under_a_random_id(client: Redis, prefix: str) -> None:
    store = RedisSessionStore(client, prefix=prefix)
    session = _session()
    first = store.create(session, idle_ttl=IDLE)
    assert first != store.create(session, idle_ttl=IDLE)
    assert store.get(first) == session
    assert store.get("missing") is None


def test_get_does_not_extend_the_idle_timeout(client: Redis, prefix: str) -> None:
    store = RedisSessionStore(client, prefix=prefix)
    session_id = store.create(_session(), idle_ttl=timedelta(seconds=10))
    key = f"{prefix}session:{session_id}"
    client.expire(key, 3)
    store.get(session_id)
    assert client.ttl(key) <= 3


def test_touch_extends_but_is_capped_at_the_absolute_expiry(
    client: Redis, prefix: str
) -> None:
    store = RedisSessionStore(client, prefix=prefix)
    session_id = store.create(
        _session(timedelta(seconds=60)), idle_ttl=timedelta(seconds=5)
    )
    key = f"{prefix}session:{session_id}"
    assert store.touch(session_id, idle_ttl=timedelta(hours=1)) is True
    assert 55 <= client.ttl(key) <= 60
    assert store.touch("missing", idle_ttl=IDLE) is False


def test_delete_removes_a_session(client: Redis, prefix: str) -> None:
    store = RedisSessionStore(client, prefix=prefix)
    session_id = store.create(_session(), idle_ttl=IDLE)
    store.delete(session_id)
    assert store.get(session_id) is None


def test_rotate_leaves_the_old_id_unreadable(client: Redis, prefix: str) -> None:
    store = RedisSessionStore(client, prefix=prefix)
    session = _session()
    old = store.create(session, idle_ttl=IDLE)
    new = store.rotate(old, idle_ttl=IDLE)
    assert new is not None
    assert new != old
    assert store.get(old) is None
    assert store.get(new) == session
    assert store.rotate(old, idle_ttl=IDLE) is None
