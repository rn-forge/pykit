"""Idempotency store protocols, request hashing, and in-memory test doubles.

Stores must claim keys atomically. Reusing a key with a different request hash
is an error; a completed key replays its stored response.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import IdempotencyKeyReuse

__all__ = [
    "AsyncIdempotencyStore",
    "IdempotencyStore",
    "InMemoryAsyncIdempotencyStore",
    "InMemoryIdempotencyStore",
    "StoredResponse",
    "request_hash",
]


def request_hash(body: Any) -> str:
    """Return a SHA-256 over a canonical JSON encoding of *body*.

    Canonical means ``sort_keys=True`` with no whitespace, so two bodies that
    differ only in key order or formatting hash identically — otherwise a
    client library that reorders JSON keys turns every retry into a 409.

    Args:
        body: Any JSON-serializable value. ``None`` is a valid body and hashes
            like any other.

    Returns:
        The hash as a lowercase hex digest.
    """
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class StoredResponse(DataclassMixin):
    """A response held against an idempotency key."""

    status: int
    body: Mapping[str, Any]
    replayed: bool = False


@runtime_checkable
class IdempotencyStore(Protocol):
    """The synchronous idempotency-key contract.

    The claim made by :meth:`record_or_replay` must be atomic.
    """

    def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None:
        """Claim *key* within *scope*, or return the response already stored.

        Args:
            scope: An opaque namespace. A tenant-scoped consumer passes the
                tenant id; an endpoint-scoped one passes the route name. Keys
                in different scopes never collide.
            key: The client's ``Idempotency-Key``.
            request_body: The request body, hashed for reuse detection.

        Returns:
            ``None`` on first sight — the caller executes and then calls
            :meth:`complete`. The stored response (with ``replayed=True``) when
            this key has already completed. ``None`` again when the key is
            claimed but still in flight; see :class:`InMemoryIdempotencyStore`
            for why that is the specified behaviour.

        Raises:
            IdempotencyKeyReuse: *key* was seen with a different body.
        """
        ...

    def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None:
        """Store the response produced for a claimed key."""
        ...


@runtime_checkable
class AsyncIdempotencyStore(Protocol):
    """The async counterpart of :class:`IdempotencyStore`, with identical semantics."""

    async def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None:
        """See :meth:`IdempotencyStore.record_or_replay`."""
        ...

    async def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None:
        """See :meth:`IdempotencyStore.complete`."""
        ...


@dataclass
class _Entry:
    """One claimed key: the body hash, and the response once it exists."""

    body_hash: str
    response: StoredResponse | None = None


class InMemoryIdempotencyStore:
    """A dict-backed :class:`IdempotencyStore` for tests.

    It holds everything forever and is not shared between processes, so it is a
    test double, not a production store. A claimed but incomplete key returns
    ``None``; implementations that distinguish in-flight duplicates must define
    their own lease behavior.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}

    def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None:
        """See :meth:`IdempotencyStore.record_or_replay`."""
        digest = request_hash(request_body)
        entry = self._entries.get((scope, key))
        if entry is None:
            self._entries[(scope, key)] = _Entry(body_hash=digest)
            return None
        if entry.body_hash != digest:
            raise IdempotencyKeyReuse(
                "Idempotency key {} was replayed with a different request body",
                key,
                error_code=409,
            )
        if entry.response is None:
            return None
        return StoredResponse(
            status=entry.response.status, body=entry.response.body, replayed=True
        )

    def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None:
        """See :meth:`IdempotencyStore.complete`."""
        entry = self._entries.get((scope, key))
        if entry is None:
            entry = _Entry(body_hash=request_hash(None))
            self._entries[(scope, key)] = entry
        entry.response = StoredResponse(status=status, body=dict(response_body))


class InMemoryAsyncIdempotencyStore:
    """An async wrapper around the in-memory test store."""

    def __init__(self) -> None:
        self._inner = InMemoryIdempotencyStore()

    async def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None:
        """See :meth:`AsyncIdempotencyStore.record_or_replay`."""
        return self._inner.record_or_replay(
            scope=scope, key=key, request_body=request_body
        )

    async def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None:
        """See :meth:`AsyncIdempotencyStore.complete`."""
        self._inner.complete(
            scope=scope, key=key, status=status, response_body=response_body
        )
