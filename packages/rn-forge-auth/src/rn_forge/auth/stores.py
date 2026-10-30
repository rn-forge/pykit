"""Server-side records: login sessions and transactions, replayed token IDs and
revoked sessions."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from rn_forge.auth.identity import LoginTransaction, SessionInfo

__all__ = [
    "InMemoryReplayStore",
    "InMemorySessionStore",
    "InMemoryTransactionStore",
    "ReplayStore",
    "SessionStore",
    "TransactionStore",
]


@runtime_checkable
class TransactionStore(Protocol):
    """Holds login transactions between the login redirect and the callback.

    Implementations shared by several processes must make :meth:`consume`
    atomic.
    """

    def save(self, transaction: LoginTransaction, *, ttl: timedelta) -> None:
        """Store *transaction* under its ``id`` for *ttl*."""
        ...

    def consume(self, transaction_id: str) -> LoginTransaction | None:
        """Remove and return the transaction with ID *transaction_id*.

        When callers race, exactly one receives the transaction.

        Returns:
            The transaction, or ``None`` when none is stored under that ID or it
            has expired.
        """
        ...


@runtime_checkable
class SessionStore(Protocol):
    """Holds login sessions under random, unguessable IDs.

    A session ends at the first of two times: its idle expiry, which
    :meth:`touch` and :meth:`rotate` extend, and ``SessionInfo.expires_at``,
    which nothing extends. A session past either is absent.
    """

    def create(self, session: SessionInfo, *, idle_ttl: timedelta) -> str:
        """Store *session* and return its new session ID.

        The session is idle-expired *idle_ttl* from now.
        """
        ...

    def get(self, session_id: str) -> SessionInfo | None:
        """Return the session, or ``None`` when absent or expired.

        Reading does not extend the idle expiry.
        """
        ...

    def touch(self, session_id: str, *, idle_ttl: timedelta) -> bool:
        """Move the idle expiry to *idle_ttl* from now, but not past ``expires_at``.

        Returns:
            ``True`` when the session exists, ``False`` otherwise.
        """
        ...

    def delete(self, session_id: str) -> None:
        """Remove the session; absent sessions are ignored."""
        ...

    def rotate(self, session_id: str, *, idle_ttl: timedelta) -> str | None:
        """Move the session to a new ID and remove the old record.

        The idle expiry restarts at *idle_ttl* from now, capped at ``expires_at``.

        Returns:
            The new session ID, or ``None`` when the session is absent or
            expired.
        """
        ...


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


class InMemoryTransactionStore:
    """:class:`TransactionStore` held in process memory.

    Thread-safe. The records are not shared across processes, so it suits tests
    and single-process deployments only.

    Args:
        clock: Returns the current time in seconds, monotonic.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[LoginTransaction, float]] = {}

    def save(self, transaction: LoginTransaction, *, ttl: timedelta) -> None:
        """See :meth:`TransactionStore.save`."""
        with self._lock:
            now = self._clock()
            self._entries = {k: v for k, v in self._entries.items() if v[1] > now}
            self._entries[transaction.id] = (transaction, now + ttl.total_seconds())

    def consume(self, transaction_id: str) -> LoginTransaction | None:
        """See :meth:`TransactionStore.consume`."""
        with self._lock:
            entry = self._entries.pop(transaction_id, None)
            if entry is None or entry[1] <= self._clock():
                return None
            return entry[0]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemorySessionStore:
    """:class:`SessionStore` held in process memory.

    Thread-safe. The sessions are not shared across processes, so it suits tests
    and single-process deployments only.

    Args:
        clock: Returns the current time as an aware datetime.
    """

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[SessionInfo, datetime]] = {}

    def create(self, session: SessionInfo, *, idle_ttl: timedelta) -> str:
        """See :meth:`SessionStore.create`."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            session_id = secrets.token_urlsafe(32)
            self._entries[session_id] = (
                session,
                self._idle_expiry(session, now, idle_ttl),
            )
            return session_id

    def get(self, session_id: str) -> SessionInfo | None:
        """See :meth:`SessionStore.get`."""
        with self._lock:
            self._purge(self._clock())
            entry = self._entries.get(session_id)
            return entry[0] if entry is not None else None

    def touch(self, session_id: str, *, idle_ttl: timedelta) -> bool:
        """See :meth:`SessionStore.touch`."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            entry = self._entries.get(session_id)
            if entry is None:
                return False
            session = entry[0]
            self._entries[session_id] = (
                session,
                self._idle_expiry(session, now, idle_ttl),
            )
            return True

    def delete(self, session_id: str) -> None:
        """See :meth:`SessionStore.delete`."""
        with self._lock:
            self._entries.pop(session_id, None)

    def rotate(self, session_id: str, *, idle_ttl: timedelta) -> str | None:
        """See :meth:`SessionStore.rotate`."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            entry = self._entries.pop(session_id, None)
            if entry is None:
                return None
            new_id = secrets.token_urlsafe(32)
            self._entries[new_id] = (
                entry[0],
                self._idle_expiry(entry[0], now, idle_ttl),
            )
            return new_id

    @staticmethod
    def _idle_expiry(
        session: SessionInfo, now: datetime, idle_ttl: timedelta
    ) -> datetime:
        return min(now + idle_ttl, session.expires_at)

    def _purge(self, now: datetime) -> None:
        self._entries = {k: v for k, v in self._entries.items() if v[1] > now}
