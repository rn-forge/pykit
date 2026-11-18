from __future__ import annotations

import os
import threading
import time
import tracemalloc
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from typing import Self

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

from rn_forge.auth import AuthorizationContext, AuthorizationContextCache

Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Provider:
    def resolve(self, account_id: str) -> AuthorizationContext:
        return AuthorizationContext(active=True, session_version=1)


class _CountingProvider(_Provider):
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, account_id: str) -> AuthorizationContext:
        self.calls += 1
        return super().resolve(account_id)


class _TimedLock:
    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock
        self._started = 0.0
        self.acquisitions = 0
        self.hold_max_s = 0.0
        self.hold_total_s = 0.0

    def __enter__(self) -> Self:
        self._lock.acquire()
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        held = time.perf_counter() - self._started
        self._lock.release()
        self.acquisitions += 1
        self.hold_max_s = max(self.hold_max_s, held)
        self.hold_total_s += held


def _new_cache(clock: _Clock, provider: _Provider) -> AuthorizationContextCache:
    return AuthorizationContextCache(provider, ttl=timedelta(seconds=60), clock=clock)


def _record_lock(counts: dict[str, int | float], lock: _TimedLock) -> None:
    counts["lock_acquisitions"] = lock.acquisitions
    counts["lock_hold_max_s"] = lock.hold_max_s
    counts["lock_hold_total_s"] = lock.hold_total_s


def _record_entries(
    counts: dict[str, int | float], cache: AuthorizationContextCache, clock: _Clock
) -> None:
    counts["entries_end"] = len(cache._entries)
    counts["live_end"] = sum(
        clock.now - entry.stored_at < 60.0 for entry in cache._entries.values()
    )


@pytest.mark.parametrize("accounts", [1000, 4000, 16000])
def test_plain_churn(accounts: int, measure: Measure) -> None:
    clock, provider = _Clock(), _Provider()
    cache = _new_cache(clock, provider)
    lock = _TimedLock(cache._lock)
    cache._lock = lock
    with measure("auth_context_churn", {"accounts": accounts}, "cpu") as counts:
        for index in range(accounts):
            clock.now = float(index)
            cache.resolve(f"a{index}")
            if (index + 1) % (accounts // 4) == 0:
                counts[f"entries_q{(index + 1) // (accounts // 4)}"] = len(
                    cache._entries
                )
        _record_entries(counts, cache, clock)
        counts["retained_bytes"] = tracemalloc.get_traced_memory()[0]
        _record_lock(counts, lock)


def test_invalidated_churn(measure: Measure) -> None:
    accounts = 16000
    clock, provider = _Clock(), _Provider()
    cache = _new_cache(clock, provider)
    lock = _TimedLock(cache._lock)
    cache._lock = lock
    with measure(
        "auth_context_churn_invalidated", {"accounts": accounts}, "cpu"
    ) as counts:
        for index in range(accounts):
            clock.now = float(index)
            account_id = f"a{index}"
            cache.resolve(account_id)
            cache.invalidate(account_id)
            if (index + 1) % 4000 == 0:
                counts[f"entries_q{(index + 1) // 4000}"] = len(cache._entries)
        _record_entries(counts, cache, clock)
        counts["version_accounts"] = len(cache._versions._accounts)
        counts["retained_bytes"] = tracemalloc.get_traced_memory()[0]
        _record_lock(counts, lock)


def test_hot_set_churn(measure: Measure) -> None:
    steps, hot = 16000, 20
    clock, provider = _Clock(), _CountingProvider()
    cache = _new_cache(clock, provider)
    lock = _TimedLock(cache._lock)
    cache._lock = lock
    with measure(
        "auth_context_churn_hot", {"steps": steps, "hot": hot}, "cpu"
    ) as counts:
        for index in range(steps):
            clock.now = float(index)
            cache.resolve(f"c{index}")
            cache.resolve(f"h{index % hot}")
            if (index + 1) % 4000 == 0:
                counts[f"entries_q{(index + 1) // 4000}"] = len(cache._entries)
        _record_entries(counts, cache, clock)
        counts["provider_calls"] = provider.calls
        counts["retained_bytes"] = tracemalloc.get_traced_memory()[0]
        _record_lock(counts, lock)
