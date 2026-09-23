"""Idempotency store protocols, request hashing, and in-memory test doubles.

Stores must claim keys atomically. Reusing a key with a different request hash
is an error (422); a claim still in flight is a distinct error (409); a
completed key replays its stored response.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import (
    IdempotencyKeyInFlight,
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
)

__all__ = [
    "IDEMPOTENCY_KEY_HEADER",
    "SAFE_METHODS",
    "AsyncIdempotencyStore",
    "IdempotencyStore",
    "InMemoryAsyncIdempotencyStore",
    "InMemoryIdempotencyStore",
    "StoredResponse",
    "check_idempotency_key",
    "request_hash",
    "run_idempotent",
    "run_idempotent_async",
]

IDEMPOTENCY_KEY_HEADER: Final = "Idempotency-Key"
"""The request header carrying the key (draft-ietf-httpapi-idempotency-key-header)."""

SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
"""Methods :func:`run_idempotent` bypasses the store for."""


def check_idempotency_key(
    value: str | None, *, header: str = IDEMPOTENCY_KEY_HEADER
) -> str:
    """Return *value*, the request's idempotency key, raising when it is absent.

    Args:
        value: The header's value, or ``None`` when absent.
        header: The header's name, for the error detail.

    Raises:
        IdempotencyKeyRequired: *value* is ``None`` or empty (400).
    """
    if not value:
        raise IdempotencyKeyRequired("{} is required", header, error_code=400)
    return value


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
            this key has already completed.

        Raises:
            IdempotencyKeyReuse: *key* was seen with a different body.
            IdempotencyKeyInFlight: *key* was claimed and its original request
                has not completed.
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
    test double, not a production store.
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
                error_code=422,
            )
        if entry.response is None:
            raise IdempotencyKeyInFlight(
                "Idempotency key {} is still processing its original request",
                key,
                error_code=409,
            )
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


def run_idempotent(
    store: IdempotencyStore,
    *,
    scope: str,
    key: str | None,
    method: str,
    body: Any,
    execute: Callable[[], tuple[int, Mapping[str, Any]]],
    header: str = IDEMPOTENCY_KEY_HEADER,
) -> StoredResponse:
    """Run *execute* under the idempotency-key protocol.

    A safe method (:data:`SAFE_METHODS`) bypasses the store entirely and just
    runs *execute*. An unsafe method requires *key*, claims it, replays a
    completed key's stored response, and stores what *execute* returns on
    first sight.

    Args:
        store: The idempotency store.
        scope: An opaque namespace for the key — see
            :meth:`IdempotencyStore.record_or_replay`.
        key: The client's ``Idempotency-Key`` header value, or ``None``.
        method: The request's HTTP method, any case.
        body: The request body, hashed for reuse detection.
        execute: Runs the handler, returning ``(status, response_body)``.
        header: The header's name, for :exc:`IdempotencyKeyRequired`'s detail.

    Returns:
        The response to send. ``replayed`` is ``True`` only for a stored
        replay.

    Raises:
        IdempotencyKeyRequired: An unsafe method and *key* is absent (400).
        IdempotencyKeyReuse: *key* was seen with a different body (422).
        IdempotencyKeyInFlight: *key* is claimed and still in flight (409).
    """
    if method.upper() in SAFE_METHODS:
        status, response_body = execute()
        return StoredResponse(status=status, body=dict(response_body))

    resolved_key = check_idempotency_key(key, header=header)
    stored = store.record_or_replay(scope=scope, key=resolved_key, request_body=body)
    if stored is not None:
        return stored
    status, response_body = execute()
    store.complete(
        scope=scope, key=resolved_key, status=status, response_body=response_body
    )
    return StoredResponse(status=status, body=dict(response_body))


async def run_idempotent_async(
    store: AsyncIdempotencyStore,
    *,
    scope: str,
    key: str | None,
    method: str,
    body: Any,
    execute: Callable[[], Awaitable[tuple[int, Mapping[str, Any]]]],
    header: str = IDEMPOTENCY_KEY_HEADER,
) -> StoredResponse:
    """See :func:`run_idempotent`; identical semantics over the async store and *execute*."""
    if method.upper() in SAFE_METHODS:
        status, response_body = await execute()
        return StoredResponse(status=status, body=dict(response_body))

    resolved_key = check_idempotency_key(key, header=header)
    stored = await store.record_or_replay(
        scope=scope, key=resolved_key, request_body=body
    )
    if stored is not None:
        return stored
    status, response_body = await execute()
    await store.complete(
        scope=scope, key=resolved_key, status=status, response_body=response_body
    )
    return StoredResponse(status=status, body=dict(response_body))
