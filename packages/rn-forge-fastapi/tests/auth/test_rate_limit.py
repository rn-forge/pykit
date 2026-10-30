"""The fixed-window counters."""

from datetime import timedelta

import pytest
from rn_forge.fastapi import InMemoryRateLimiter, RateLimit, RateLimiter

pytestmark = pytest.mark.unit

RATE = RateLimit(2, timedelta(seconds=60))


def test_the_limiter_satisfies_the_protocol():
    assert isinstance(InMemoryRateLimiter(), RateLimiter)


def test_hits_within_the_limit_pass_and_the_next_reports_the_window_end():
    limiter = InMemoryRateLimiter(clock=lambda: 125.0)

    results = [limiter.hit("login", "a", RATE) for _ in range(4)]

    assert results == [None, None, 55, 55]


def test_scopes_and_subjects_count_apart():
    limiter = InMemoryRateLimiter(clock=lambda: 0.0)
    for _ in range(2):
        limiter.hit("login", "a", RATE)

    assert limiter.hit("login", "b", RATE) is None
    assert limiter.hit("callback", "a", RATE) is None
    assert limiter.hit("login", "a", RATE) is not None


def test_a_new_window_starts_a_new_count():
    now = [0.0]
    limiter = InMemoryRateLimiter(clock=lambda: now[0])
    for _ in range(3):
        limiter.hit("login", "a", RATE)

    now[0] = 60.0

    assert limiter.hit("login", "a", RATE) is None


def test_expired_windows_are_dropped():
    now = [0.0]
    limiter = InMemoryRateLimiter(clock=lambda: now[0])
    limiter.hit("login", "a", RATE)

    now[0] = 600.0
    limiter.hit("login", "b", RATE)

    assert len(limiter._counts) == 1
