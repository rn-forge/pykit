"""Idempotency keys: the store protocol, request hashing and a test double.

A client retrying an unsafe request sends the same ``Idempotency-Key``; the
server executes once and replays the stored response thereafter. This module
declares the contract both framework packages implement and neither invents.

Three properties the protocol requires, all of which are easy to lose
---------------------------------------------------------------------

1. **The request body is hashed.** Replaying a key with a *different* body is a
   client bug, and :func:`request_hash` makes it detectable
   (:class:`~rn_forge.web.exceptions.IdempotencyKeyReuse`, 409) rather than a
   silently-wrong cached response. This is the single most valuable thing here.
2. **The protocol is two-phase.** :meth:`~IdempotencyStore.record_or_replay`
   returns ``None`` on first sight — the caller executes, then calls
   :meth:`~IdempotencyStore.complete` — or the stored response on a replay. A
   ``replay``/``remember`` pair with no constraint tying the two writes lets two
   concurrent first-sight requests both execute.
3. **Race safety comes from a uniqueness constraint, not a check-then-insert.**
   An implementer requirement, not an implementation detail: a SQL adapter uses
   ``INSERT ... ON CONFLICT DO NOTHING`` against a ``UNIQUE (scope, key)``
   constraint and reads the row back; a cache adapter uses an atomic
   set-if-absent (Django's ``cache.add()``). A ``get``-then-``set`` adapter
   silently loses the property, and its tests will not notice.

Sync and async are two protocols, not one
-----------------------------------------

A SQLAlchemy store is ``async def`` against an ``AsyncSession``; a Django cache
store is a sync call. Two ``Protocol`` classes with identical method shapes are the
honest way to say that; a single protocol returning ``Awaitable[...] | ...``
is not.
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

    Implementers must satisfy property 3 in the module docstring: the claim
    made by ``record_or_replay`` is atomic, so two concurrent first-sight
    requests do not both receive ``None``.
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
    """A dict-backed :class:`IdempotencyStore`. **For tests.**

    It holds everything forever and is not shared between processes, so it is a
    test double and a local-development convenience, never a deployment.

    In-flight replays
    -----------------

    A key that has been claimed but whose ``complete`` has not yet been called
    returns ``None`` — the same as first sight. That is the specified
    behaviour, and it is a deliberate choice rather than an oversight: an
    in-flight duplicate is indistinguishable from a first request that crashed
    before completing, and returning a distinct "in progress" signal would
    require every adapter to also decide when a claim expires. A consumer that
    needs 409-on-concurrent-duplicate implements it in its own adapter with a
    lease timeout, and this docstring is where that decision is recorded.
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
    """A dict-backed :class:`AsyncIdempotencyStore`. **For tests.**

    A separate class rather than extra methods on
    :class:`InMemoryIdempotencyStore`: one object cannot carry both a ``def``
    and an ``async def`` under the same name, and giving the async one a
    different name would make it satisfy neither protocol. It delegates to a
    sync store, so the two doubles cannot drift.
    """

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
