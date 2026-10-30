"""Fixed-window rate limiting for the login and callback routes."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, runtime_checkable

__all__ = [
    "InMemoryRateLimiter",
    "RateLimit",
    "RateLimiter",
    "window_key",
    "window_seconds",
]


@dataclass(frozen=True)
class RateLimit:
    """At most *limit* hits in each *window*.

    Attributes:
        limit: The hits one window allows.
        window: The length of a window.
    """

    limit: int
    window: timedelta


@runtime_checkable
class RateLimiter(Protocol):
    """Counts hits per scope and subject in fixed windows.

    Windows are aligned to the clock, so a client can use a limit twice around
    a window boundary. Every method is synchronous and thread-safe.
    """

    def hit(self, scope: str, subject: str, rate: RateLimit) -> int | None:
        """Count one hit of *subject* in *scope*.

        Returns:
            ``None`` while within *rate*, otherwise the seconds until the
            window ends.
        """
        ...


def window_seconds(rate: RateLimit) -> int:
    """The length of *rate*'s window in whole seconds, at least one."""
    return max(1, math.ceil(rate.window.total_seconds()))


def window_key(scope: str, subject: str, rate: RateLimit, now: float) -> str:
    """The counter key for a hit at *now*: a digest, so *subject* is never stored."""
    digest = hashlib.sha256(f"{scope}\0{subject}".encode()).hexdigest()
    return f"{digest}:{int(now // window_seconds(rate))}"


class InMemoryRateLimiter:
    """:class:`RateLimiter` held in process memory, for tests and development.

    Args:
        clock: Returns the current time in seconds.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, scope: str, subject: str, rate: RateLimit) -> int | None:
        """Count one hit of *subject* in *scope*."""
        window = window_seconds(rate)
        now = self._clock()
        key = window_key(scope, subject, rate, now)
        ends = (int(now // window) + 1) * window
        with self._lock:
            self._counts = {
                k: held for k, held in self._counts.items() if held[1] > now
            }
            count = self._counts.get(key, (0, ends))[0] + 1
            self._counts[key] = (count, ends)
        if count <= rate.limit:
            return None
        return max(1, math.ceil(ends - now))
