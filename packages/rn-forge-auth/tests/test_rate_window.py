from datetime import timedelta
from hashlib import sha256

import pytest


@pytest.mark.parametrize(
    ("window", "expected"),
    [(timedelta(milliseconds=200), 1), (timedelta(seconds=60, milliseconds=100), 61)],
)
def test_window_is_whole_seconds_at_least_one(window: timedelta, expected: int) -> None:
    from rn_forge.auth.rate_window import fixed_window_seconds

    assert fixed_window_seconds(window) == expected


def test_key_is_a_digest_of_scope_and_subject_plus_bucket() -> None:
    from rn_forge.auth.rate_window import fixed_window_key

    start = 60.0
    one_second_later = 61.0
    next_bucket = 120.0
    first = fixed_window_key("scope", "secret-subject", 60, start)
    digest = sha256(b"scope\0secret-subject").hexdigest()
    assert first == f"{digest}:1"
    assert "secret-subject" not in first
    assert fixed_window_key("scope", "secret-subject", 60, one_second_later) == first
    assert fixed_window_key("scope", "secret-subject", 60, next_bucket) != first


def test_scope_and_subject_are_separated() -> None:
    from rn_forge.auth.rate_window import fixed_window_key

    now = 60.0
    assert fixed_window_key("a", "bc", 60, now) != fixed_window_key("ab", "c", 60, now)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (60.0, 60),
        (77.0, 43),
        (119.8, 1),
        (119.0, 1),
        (120.0, 60),
    ],
)
def test_retry_after_counts_to_the_window_end(now: float, expected: int) -> None:
    from rn_forge.auth.rate_window import fixed_window_retry_after

    assert fixed_window_retry_after(60, now) == max(1, 60 - int(now) % 60)
    assert fixed_window_retry_after(60, now) == expected
