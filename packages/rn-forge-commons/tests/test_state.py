"""Tests for rn_forge.commons.state."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.state import StateStore


@dataclass
class ArtifactState(DataclassMixin):
    hash: str
    source_layer: str = "default"


class TestStateStore:
    def test_round_trip_typed_entries(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record("a", ArtifactState(hash="abc"))
        assert store.get("a") == ArtifactState(hash="abc")

    def test_record_many_writes_once(self, tmp_path, monkeypatch):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        write_calls = []
        original_write = StateStore._write

        def counting_write(self, data):
            write_calls.append(1)
            original_write(self, data)

        monkeypatch.setattr(StateStore, "_write", counting_write)
        store.record_many({"a": ArtifactState(hash="1"), "b": ArtifactState(hash="2")})
        assert len(write_calls) == 1
        assert store.get("a") == ArtifactState(hash="1")
        assert store.get("b") == ArtifactState(hash="2")

    def test_corrupt_state_file_raises_naming_the_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("not json{{{")
        store = StateStore(state_file, entry_type=ArtifactState)
        with pytest.raises(AppException, match=str(state_file)):
            store.load()

    def test_truncated_entry_raises(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text('{"schema_version": "1", "entries": {"a": {}}}')
        store = StateStore(state_file, entry_type=ArtifactState)
        with pytest.raises(AppException):
            store.load()

    def test_unexpected_schema_version_rejected(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text('{"schema_version": "99", "entries": {}}')
        store = StateStore(state_file, entry_type=ArtifactState, schema_version="1")
        with pytest.raises(AppException):
            store.load()

    def test_concurrent_record_from_two_threads_does_not_lose_entries(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)

        def worker(prefix: str) -> None:
            for i in range(20):
                store.record(f"{prefix}-{i}", ArtifactState(hash=str(i)))

        threads = [threading.Thread(target=worker, args=(p,)) for p in ("x", "y")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = store.load()
        assert len(loaded) == 40

    def test_remove(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record("a", ArtifactState(hash="1"))
        store.remove("a")
        assert store.get("a") is None

    def test_stale_keys_with_custom_predicate(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record("present", ArtifactState(hash="1"))
        store.record("absent", ArtifactState(hash="2"))
        stale = store.stale_keys(exists=lambda key: key == "present")
        assert stale == ["absent"]

    def test_load_missing_file_returns_empty(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        assert store.load() == {}


class TestContentHash:
    def test_of_deterministic(self):
        from rn_forge.commons.utils import ContentHash

        assert ContentHash.of("hello") == ContentHash.of("hello")
        assert ContentHash.of("hello") != ContentHash.of("world")

    def test_of_str_and_bytes_equivalent(self):
        from rn_forge.commons.utils import ContentHash

        assert ContentHash.of("hello") == ContentHash.of(b"hello")

    def test_of_file_missing_returns_none(self, tmp_path):
        from rn_forge.commons.utils import ContentHash

        assert ContentHash.of_file(tmp_path / "missing") is None

    def test_of_file_directory_returns_none(self, tmp_path):
        from rn_forge.commons.utils import ContentHash

        assert ContentHash.of_file(tmp_path) is None

    def test_of_file_matches_of_content(self, tmp_path):
        from rn_forge.commons.utils import ContentHash

        path = tmp_path / "f.txt"
        path.write_text("hello")
        assert ContentHash.of_file(path) == ContentHash.of("hello")
