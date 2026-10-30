from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.auth import LoginTransaction
from rn_forge.django.auth.stores import CacheReplayStore, CacheTransactionStore

pytestmark = pytest.mark.unit

TTL = timedelta(seconds=30)


def _transaction(id: str = "tx-1") -> LoginTransaction:
    return LoginTransaction(
        id=id,
        provider="acme",
        return_to="/orders",
        created_at=datetime(2026, 10, 28, tzinfo=UTC),
        state="s",
        nonce="n",
        code_verifier="v",
        extra={"k": "v"},
    )


class TestCacheTransactionStore:
    def test_consume_returns_what_was_saved(self) -> None:
        store = CacheTransactionStore()
        store.save(_transaction(), ttl=TTL)

        assert store.consume("tx-1") == _transaction()

    def test_a_transaction_is_consumed_once(self) -> None:
        store = CacheTransactionStore()
        store.save(_transaction(), ttl=TTL)
        store.consume("tx-1")

        assert store.consume("tx-1") is None

    def test_an_unknown_transaction_is_none(self) -> None:
        assert CacheTransactionStore().consume("nope") is None

    def test_racing_consumers_get_it_once(self) -> None:
        store = CacheTransactionStore()
        store.save(_transaction(), ttl=TTL)
        barrier = threading.Barrier(8)
        results: list[LoginTransaction | None] = []

        def consume() -> None:
            barrier.wait()
            results.append(store.consume("tx-1"))

        threads = [threading.Thread(target=consume) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sum(result is not None for result in results) == 1


class TestCacheReplayStore:
    def test_record_once_accepts_a_key_once(self) -> None:
        store = CacheReplayStore()

        assert store.record_once("jti-1", ttl=TTL) is True
        assert store.record_once("jti-1", ttl=TTL) is False
        assert store.record_once("jti-2", ttl=TTL) is True

    def test_a_revoked_sid_is_revoked_for_its_issuer_only(self) -> None:
        store = CacheReplayStore()
        store.revoke_sid("https://idp.example", "sid-1", ttl=TTL)

        assert store.is_sid_revoked("https://idp.example", "sid-1") is True
        assert store.is_sid_revoked("https://other.example", "sid-1") is False
        assert store.is_sid_revoked("https://idp.example", "sid-2") is False

    def test_a_sid_record_does_not_collide_with_a_seen_key(self) -> None:
        store = CacheReplayStore()
        store.revoke_sid("iss", "x", ttl=TTL)

        assert store.record_once("x", ttl=TTL) is True
