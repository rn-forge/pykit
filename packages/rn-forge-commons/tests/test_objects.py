"""Tests for rn_forge.commons.objects."""

from __future__ import annotations

from datetime import timedelta

import pytest

from rn_forge.commons.objects import (
    AsyncObjectStore,
    InMemoryObjectStore,
    ObjectNotFound,
    ObjectStore,
)


class TestInMemoryObjectStore:
    def test_put_get_round_trip_preserves_bytes_exactly(self) -> None:
        store = InMemoryObjectStore()
        store.put("k", b"\x00\x01binary\xff")
        assert store.get("k") == b"\x00\x01binary\xff"

    def test_get_missing_raises(self) -> None:
        store = InMemoryObjectStore()
        with pytest.raises(ObjectNotFound):
            store.get("missing")

    def test_delete_removes(self) -> None:
        store = InMemoryObjectStore()
        store.put("k", b"data")
        store.delete("k")
        assert not store.exists("k")

    def test_delete_missing_is_idempotent_no_op(self) -> None:
        store = InMemoryObjectStore()
        store.delete("missing")  # must not raise

    def test_exists_both_ways(self) -> None:
        store = InMemoryObjectStore()
        assert store.exists("k") is False
        store.put("k", b"data")
        assert store.exists("k") is True

    def test_url_for_raises_on_in_memory_store(self) -> None:
        store = InMemoryObjectStore()
        store.put("k", b"data")
        with pytest.raises(NotImplementedError):
            store.url_for("k", expires_in=timedelta(minutes=5))

    def test_satisfies_object_store_protocol(self) -> None:
        assert isinstance(InMemoryObjectStore(), ObjectStore)

    def test_satisfies_async_object_store_protocol_structurally(self) -> None:
        assert isinstance(InMemoryObjectStore(), AsyncObjectStore)
