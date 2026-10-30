"""In-process cache of authorization contexts."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, runtime_checkable

from rn_forge.auth.context import AuthorizationContext, AuthorizationContextProvider

__all__ = [
    "AccountStateWriter",
    "AuthorizationContextCache",
    "AuthorizationVersions",
    "InMemoryAuthorizationVersions",
]


@runtime_checkable
class AuthorizationVersions(Protocol):
    """Counters that say when cached authorization contexts are stale."""

    def current(self, account_id: str) -> tuple[int, int]:
        """Return the account's version and the global version."""
        ...

    def bump(self, account_id: str) -> None:
        """Increase the version of *account_id*."""
        ...

    def bump_all(self) -> None:
        """Increase the global version, which every account shares."""
        ...


class InMemoryAuthorizationVersions:
    """:class:`AuthorizationVersions` held in process memory.

    Thread-safe. The counters are not shared across processes, so a bump is
    seen only by caches that use the same instance.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accounts: dict[str, int] = {}
        self._global = 0

    def current(self, account_id: str) -> tuple[int, int]:
        """Return the account's version and the global version."""
        with self._lock:
            return self._accounts.get(account_id, 0), self._global

    def bump(self, account_id: str) -> None:
        """Increase the version of *account_id*."""
        with self._lock:
            self._accounts[account_id] = self._accounts.get(account_id, 0) + 1

    def bump_all(self) -> None:
        """Increase the global version."""
        with self._lock:
            self._global += 1


class AccountStateWriter(Protocol):
    """Persists the account state that an authorization context carries."""

    def set_active(self, account_id: str, active: bool) -> None:
        """Store whether *account_id* may authenticate."""
        ...

    def bump_session_version(self, account_id: str) -> int:
        """Increase the session version of *account_id* and return the new one."""
        ...


@dataclass(frozen=True)
class _Entry:
    context: AuthorizationContext
    versions: tuple[int, int]
    stored_at: float


class AuthorizationContextCache:
    """An :class:`AuthorizationContextProvider` that caches another one.

    Each account has one entry, valid while the account and global versions are
    those it was computed at and it is younger than *ttl*. Changes made
    through :meth:`invalidate`, :meth:`invalidate_all`, :meth:`set_active` and
    :meth:`bump_session_version` apply on the next :meth:`resolve`. A change
    made any other way applies once the entry's *ttl* has passed. The cache is
    safe to share between threads and is local to the process.

    Args:
        provider: The provider that computes contexts.
        ttl: The longest an entry is served. Must be positive.
        versions: The version counters. Defaults to a new
            :class:`InMemoryAuthorizationVersions`.
        writer: Persists account state for :meth:`set_active` and
            :meth:`bump_session_version`.
        clock: Returns the current time in seconds, monotonic.

    Raises:
        ValueError: *ttl* is not positive.
    """

    def __init__(
        self,
        provider: AuthorizationContextProvider,
        *,
        ttl: timedelta = timedelta(seconds=60),
        versions: AuthorizationVersions | None = None,
        writer: AccountStateWriter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._provider = provider
        self._ttl = ttl.total_seconds()
        self._versions = (
            versions if versions is not None else InMemoryAuthorizationVersions()
        )
        self._writer = writer
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def resolve(self, account_id: str) -> AuthorizationContext:
        """Return the context of *account_id*, computing it on a miss."""
        versions = self._versions.current(account_id)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(account_id)
        if (
            entry is not None
            and entry.versions == versions
            and now - entry.stored_at < self._ttl
        ):
            return entry.context
        # Versions were read before the provider so a bump during the
        # computation leaves the entry stale rather than fresh.
        context = self._provider.resolve(account_id)
        with self._lock:
            self._entries[account_id] = _Entry(context, versions, now)
        return context

    def invalidate(self, account_id: str) -> None:
        """Make the next :meth:`resolve` of *account_id* recompute."""
        self._versions.bump(account_id)

    def invalidate_all(self) -> None:
        """Make the next :meth:`resolve` of every account recompute."""
        self._versions.bump_all()

    def set_active(self, account_id: str, active: bool) -> None:
        """Store the account's ``active`` flag and invalidate its context.

        Raises:
            RuntimeError: No writer was configured.
        """
        self._require_writer().set_active(account_id, active)
        self.invalidate(account_id)

    def bump_session_version(self, account_id: str) -> int:
        """Increase the account's session version and invalidate its context.

        Returns:
            The new session version.

        Raises:
            RuntimeError: No writer was configured.
        """
        version = self._require_writer().bump_session_version(account_id)
        self.invalidate(account_id)
        return version

    def _require_writer(self) -> AccountStateWriter:
        if self._writer is None:
            raise RuntimeError("no AccountStateWriter was configured")
        return self._writer
