"""Fixed-window rate limiting over Django's cache."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.core.cache import caches
from rn_forge.auth import (
    fixed_window_key,
    fixed_window_retry_after,
    fixed_window_seconds,
)

__all__ = ["FixedWindowLimiter", "RateLimit"]


@dataclass(frozen=True)
class RateLimit:
    """At most *limit* hits in each *window*.

    Attributes:
        limit: The hits one window allows.
        window: The length of a window.
    """

    limit: int
    window: timedelta


class FixedWindowLimiter:
    """Counts hits per key in fixed windows.

    The counter is ``cache.add`` followed by ``cache.incr``, so the processes
    that share the cache share the count. Windows are aligned to the clock, so
    a client can use a limit twice around a window boundary.

    Args:
        alias: The cache alias in ``CACHES``.
        prefix: Prepended to every key.
        clock: Returns the current time in seconds.

    Attributes:
        alias: The cache alias in ``CACHES``.
    """

    def __init__(
        self,
        *,
        alias: str = "default",
        prefix: str = "rn-forge:rate:",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.alias = alias
        self._prefix = prefix
        self._clock = clock

    def hit(self, scope: str, subject: str, rate: RateLimit) -> int | None:
        """Count one hit of *subject* in *scope*.

        Returns:
            ``None`` while within *rate*, otherwise the seconds until the
            window ends.
        """
        window = fixed_window_seconds(rate.window)
        now = self._clock()
        key = self._prefix + fixed_window_key(scope, subject, window, now)
        cache = caches[self.alias]
        if cache.add(key, 1, window):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:  # the window ended between add and incr
                cache.add(key, 1, window)
                count = 1
        if count <= rate.limit:
            return None
        return fixed_window_retry_after(window, now)
