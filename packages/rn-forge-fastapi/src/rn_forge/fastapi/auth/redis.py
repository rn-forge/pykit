"""Redis implementation of the CSRF token store.

Requires the ``redis`` extra and Redis 6.2 or later. Not imported by
``rn_forge.fastapi``.
"""

from __future__ import annotations

import math
from datetime import timedelta

from redis import Redis

__all__ = ["RedisCsrfStore"]

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
