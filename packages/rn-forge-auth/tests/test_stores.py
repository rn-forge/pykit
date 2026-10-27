"""Tests for rn_forge.auth.stores."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from rn_forge.auth import InMemoryReplayStore, ReplayStore

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
