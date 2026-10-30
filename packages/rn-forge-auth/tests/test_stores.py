"""Tests for rn_forge.auth.stores."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.auth import (
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    LoginTransaction,
    ReplayStore,
    SessionInfo,
    SessionStore,
    TransactionStore,
)

pytestmark = pytest.mark.unit

TTL = timedelta(seconds=10)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_in_memory_store_satisfies_the_protocol() -> None:
    assert isinstance(InMemoryReplayStore(), ReplayStore)


def test_record_once_is_true_only_the_first_time() -> None:
    store = InMemoryReplayStore()
    assert store.record_once("a", ttl=TTL) is True
    assert store.record_once("a", ttl=TTL) is False
    assert store.record_once("b", ttl=TTL) is True


def test_a_record_expires_after_its_ttl() -> None:
    clock = _Clock()
    store = InMemoryReplayStore(clock=clock)
    store.record_once("a", ttl=TTL)
    clock.now += 9
    assert store.record_once("a", ttl=TTL) is False
    clock.now += 2
    assert store.record_once("a", ttl=TTL) is True


def test_concurrent_record_once_has_one_winner() -> None:
    store = InMemoryReplayStore()
    results: list[bool] = []
    barrier = threading.Barrier(16)

    def attempt() -> None:
        barrier.wait()
        results.append(store.record_once("same", ttl=TTL))

    threads = [threading.Thread(target=attempt) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1


def test_a_revoked_sid_is_revoked_until_its_ttl_passes() -> None:
    clock = _Clock()
    store = InMemoryReplayStore(clock=clock)
    assert store.is_sid_revoked("iss", "s1") is False
    store.revoke_sid("iss", "s1", ttl=TTL)
    assert store.is_sid_revoked("iss", "s1") is True
    assert store.is_sid_revoked("other-iss", "s1") is False
    assert store.is_sid_revoked("iss", "s2") is False
    clock.now += 11
    assert store.is_sid_revoked("iss", "s1") is False


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class _WallClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def _transaction(transaction_id: str = "tx1") -> LoginTransaction:
    return LoginTransaction(
        id=transaction_id,
        provider="idp",
        return_to="/home",
        created_at=NOW,
        state="s",
        nonce="n",
        code_verifier="v",
        extra={"k": "v"},
    )


def _session(expires_in: timedelta = timedelta(hours=12)) -> SessionInfo:
    return SessionInfo(
        account_id="acct",
        session_version=3,
        provider="idp",
        issuer="https://iss",
        external_subject="sub",
        created_at=NOW,
        expires_at=NOW + expires_in,
        auth_time=NOW,
        amr=frozenset({"pwd", "mfa"}),
        session_ref="sid1",
        id_token="tok",
    )


def test_the_in_memory_stores_satisfy_their_protocols() -> None:
    assert isinstance(InMemoryTransactionStore(), TransactionStore)
    assert isinstance(InMemorySessionStore(), SessionStore)


def test_a_transaction_is_consumed_once() -> None:
    store = InMemoryTransactionStore()
    store.save(_transaction(), ttl=TTL)
    assert store.consume("tx1") == _transaction()
    assert store.consume("tx1") is None
    assert store.consume("missing") is None


def test_a_transaction_expires_after_its_ttl() -> None:
    clock = _Clock()
    store = InMemoryTransactionStore(clock=clock)
    store.save(_transaction(), ttl=TTL)
    clock.now += 10
    assert store.consume("tx1") is None


def test_50_concurrent_consumes_of_a_transaction_have_one_winner() -> None:
    store = InMemoryTransactionStore()
    store.save(_transaction(), ttl=TTL)
    barrier = threading.Barrier(50)

    def attempt() -> LoginTransaction | None:
        barrier.wait()
        return store.consume("tx1")

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = [f.result() for f in [pool.submit(attempt) for _ in range(50)]]
    assert len([r for r in results if r is not None]) == 1


IDLE = timedelta(minutes=30)


def test_a_session_round_trips_under_a_random_id() -> None:
    store = InMemorySessionStore(clock=_WallClock())
    first = store.create(_session(), idle_ttl=IDLE)
    second = store.create(_session(), idle_ttl=IDLE)
    assert first != second
    assert len(first) >= 43
    assert store.get(first) == _session()
    assert store.get("missing") is None


def test_get_does_not_extend_the_idle_timeout() -> None:
    clock = _WallClock()
    store = InMemorySessionStore(clock=clock)
    session_id = store.create(_session(), idle_ttl=IDLE)
    clock.now += timedelta(minutes=29)
    assert store.get(session_id) is not None
    clock.now += timedelta(minutes=2)
    assert store.get(session_id) is None


def test_touch_extends_the_idle_timeout() -> None:
    clock = _WallClock()
    store = InMemorySessionStore(clock=clock)
    session_id = store.create(_session(), idle_ttl=IDLE)
    clock.now += timedelta(minutes=29)
    assert store.touch(session_id, idle_ttl=IDLE) is True
    clock.now += timedelta(minutes=29)
    assert store.get(session_id) is not None
    assert store.touch("missing", idle_ttl=IDLE) is False


def test_touch_never_extends_past_the_absolute_expiry() -> None:
    clock = _WallClock()
    store = InMemorySessionStore(clock=clock)
    session_id = store.create(_session(timedelta(minutes=40)), idle_ttl=IDLE)
    clock.now += timedelta(minutes=20)
    store.touch(session_id, idle_ttl=IDLE)
    clock.now += timedelta(minutes=19)
    assert store.get(session_id) is not None
    clock.now += timedelta(minutes=2)
    assert store.get(session_id) is None


def test_delete_removes_a_session() -> None:
    store = InMemorySessionStore(clock=_WallClock())
    session_id = store.create(_session(), idle_ttl=IDLE)
    store.delete(session_id)
    store.delete(session_id)
    assert store.get(session_id) is None


def test_rotate_leaves_the_old_id_unreadable() -> None:
    store = InMemorySessionStore(clock=_WallClock())
    old = store.create(_session(), idle_ttl=IDLE)
    new = store.rotate(old, idle_ttl=IDLE)
    assert new is not None
    assert new != old
    assert store.get(old) is None
    assert store.get(new) == _session()
    assert store.rotate(old, idle_ttl=IDLE) is None
