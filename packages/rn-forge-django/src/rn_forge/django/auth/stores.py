"""Login transactions, replay records and revoked session IDs in Django's cache.

The records are shared between processes only when the cache is, as Django's
Redis backend (the ``redis`` extra) is. The local-memory cache is for tests and
single-process development.
"""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta
from typing import Any

from django.core.cache import caches
from rn_forge.auth import (
    LoginTransaction,
    transaction_from_record,
    transaction_to_record,
)

__all__ = ["CacheReplayStore", "CacheTransactionStore"]


def _timeout(ttl: timedelta) -> int:
    # Django reads a timeout of 0 as "expire immediately".
    return max(1, math.ceil(ttl.total_seconds()))


def _key(prefix: str, *parts: str) -> str:
    # Hashed so an issuer URL or opaque ID cannot break a backend's key rules.
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
    return f"{prefix}{digest}"


class CacheTransactionStore:
    """:class:`~rn_forge.auth.TransactionStore` over a Django cache.

    Args:
        alias: The cache alias in ``CACHES``.
        prefix: Prepended to every key.

    Attributes:
        alias: The cache alias in ``CACHES``.
    """

    def __init__(self, *, alias: str = "default", prefix: str = "rn-forge:tx:") -> None:
        self.alias = alias
        self._prefix = prefix

    def save(self, transaction: LoginTransaction, *, ttl: timedelta) -> None:
        """See :meth:`rn_forge.auth.TransactionStore.save`."""
        document = transaction_to_record(transaction)
        caches[self.alias].set(
            _key(self._prefix, transaction.id), document, _timeout(ttl)
        )

    def consume(self, transaction_id: str) -> LoginTransaction | None:
        """See :meth:`rn_forge.auth.TransactionStore.consume`."""
        cache = caches[self.alias]
        key = _key(self._prefix, transaction_id)
        document: dict[str, Any] | None = cache.get(key)
        # Of the callers that read the record, only the one whose delete finds
        # it still there receives it.
        if document is None or not cache.delete(key):
            return None
        return transaction_from_record(document)


class CacheReplayStore:
    """:class:`~rn_forge.auth.ReplayStore` over a Django cache.

    Args:
        alias: The cache alias in ``CACHES``.
        prefix: Prepended to every key.

    Attributes:
        alias: The cache alias in ``CACHES``.
    """

    def __init__(
        self, *, alias: str = "default", prefix: str = "rn-forge:replay:"
    ) -> None:
        self.alias = alias
        self._prefix = prefix

    def record_once(self, key: str, *, ttl: timedelta) -> bool:
        """See :meth:`rn_forge.auth.ReplayStore.record_once`."""
        return caches[self.alias].add(_key(self._prefix, "seen", key), 1, _timeout(ttl))

    def revoke_sid(self, issuer: str, sid: str, *, ttl: timedelta) -> None:
        """See :meth:`rn_forge.auth.ReplayStore.revoke_sid`."""
        caches[self.alias].set(_key(self._prefix, "sid", issuer, sid), 1, _timeout(ttl))

    def is_sid_revoked(self, issuer: str, sid: str) -> bool:
        """See :meth:`rn_forge.auth.ReplayStore.is_sid_revoked`."""
        return (
            caches[self.alias].get(_key(self._prefix, "sid", issuer, sid)) is not None
        )
