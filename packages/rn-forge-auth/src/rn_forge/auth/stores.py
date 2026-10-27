"""Single-use and revocation records: replayed token IDs and revoked sessions."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol, runtime_checkable

__all__ = ["InMemoryReplayStore", "ReplayStore"]


@runtime_checkable
class ReplayStore(Protocol):
    """Records that a value was seen once, and which sessions are revoked.

    Every record expires after its ``ttl``. Implementations shared by several
    processes must make :meth:`record_once` atomic.
    """

    def record_once(self, key: str, *, ttl: timedelta) -> bool:
        """Record *key* for *ttl* unless it is already recorded.

        Returns:
            ``True`` when *key* was newly recorded, ``False`` when a record that
            has not expired was already present.
        """
        ...

    def revoke_sid(self, issuer: str, sid: str, *, ttl: timedelta) -> None:
        """Mark the session *sid* of *issuer* revoked for *ttl*."""
        ...

    def is_sid_revoked(self, issuer: str, sid: str) -> bool:
        """Return whether the session *sid* of *issuer* is currently revoked."""
        ...


class InMemoryReplayStore:
    """:class:`ReplayStore` held in process memory.

    Thread-safe. The records are not shared across processes, so it suits tests
    and single-process deployments only.

    Args:
        clock: Returns the current time in seconds, monotonic.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}
        self._revoked: dict[tuple[str, str], float] = {}

    def record_once(self, key: str, *, ttl: timedelta) -> bool:
        """See :meth:`ReplayStore.record_once`."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            if key in self._seen:
                return False
            self._seen[key] = now + ttl.total_seconds()
            return True

    def revoke_sid(self, issuer: str, sid: str, *, ttl: timedelta) -> None:
        """See :meth:`ReplayStore.revoke_sid`."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            self._revoked[(issuer, sid)] = now + ttl.total_seconds()

    def is_sid_revoked(self, issuer: str, sid: str) -> bool:
        """See :meth:`ReplayStore.is_sid_revoked`."""
        with self._lock:
            return self._revoked.get((issuer, sid), 0.0) > self._clock()

    def _purge(self, now: float) -> None:
        self._seen = {k: t for k, t in self._seen.items() if t > now}
        self._revoked = {k: t for k, t in self._revoked.items() if t > now}
