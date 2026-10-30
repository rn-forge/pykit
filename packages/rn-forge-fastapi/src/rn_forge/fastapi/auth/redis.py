"""Redis implementations of the CSRF token store and the rate limiter.

Requires the ``redis`` extra and Redis 6.2 or later. Not imported by
``rn_forge.fastapi``.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import timedelta

from redis import Redis
from rn_forge.fastapi.auth.rate_limit import RateLimit, window_key, window_seconds

__all__ = ["RedisCsrfStore", "RedisRateLimiter"]

DEFAULT_PREFIX = "rn-forge-fastapi:"


class RedisCsrfStore:
    """:class:`~rn_forge.fastapi.auth.csrf.CsrfStore` over Redis.

    Each token is one key written with ``SET ... EX``.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
    """

    def __init__(self, client: Redis, *, prefix: str = DEFAULT_PREFIX) -> None:
        self._client = client
        self._prefix = f"{prefix}csrf:"

    def save(self, key: str, token: str, *, ttl: timedelta) -> None:
        """Store *token* under *key* with ``SET ... EX``."""
        self._client.set(
            self._prefix + key, token, ex=max(1, math.ceil(ttl.total_seconds()))
        )

    def get(self, key: str) -> str | None:
        """Return the token under *key*."""
        value: object = self._client.get(self._prefix + key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def delete(self, key: str) -> None:
        """Remove the token under *key*."""
        self._client.delete(self._prefix + key)


class RedisRateLimiter:
    """:class:`~rn_forge.fastapi.auth.rate_limit.RateLimiter` over Redis.

    Each window is one key, counted with ``INCR`` and given a lifetime of one
    window with ``EXPIRE``, in one transaction.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
        clock: Returns the current time in seconds.
    """

    def __init__(
        self,
        client: Redis,
        *,
        prefix: str = DEFAULT_PREFIX,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._prefix = f"{prefix}rate:"
        self._clock = clock

    def hit(self, scope: str, subject: str, rate: RateLimit) -> int | None:
        """Count one hit of *subject* in *scope*."""
        window = window_seconds(rate)
        now = self._clock()
        key = self._prefix + window_key(scope, subject, rate, now)
        pipeline = self._client.pipeline()  # pyright: ignore[reportUnknownMemberType]  # redis-py leaves shard_hint untyped
        pipeline.incr(key)
        pipeline.expire(key, window)
        count = int(pipeline.execute()[0])
        if count <= rate.limit:
            return None
        return max(1, math.ceil((int(now // window) + 1) * window - now))
