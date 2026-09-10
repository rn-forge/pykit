"""Tests for rn_forge.tooling.state."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

import pytest

from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.tooling.state import StateStore


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


class TestMetadata:
    def test_metadata_is_written_beside_the_entries(self, tmp_path):
        store = StateStore(
            tmp_path / "state.json",
            entry_type=ArtifactState,
            metadata={"kiln_version": "0.1.0", "config_hash": "abc"},
        )
        store.record("a", ArtifactState(hash="1"))
        document = json.loads((tmp_path / "state.json").read_text())
        assert document["metadata"] == {"kiln_version": "0.1.0", "config_hash": "abc"}
        assert set(document["entries"]) == {"a"}

    def test_metadata_reads_back_what_the_last_writer_recorded(self, tmp_path):
        path = tmp_path / "state.json"
        StateStore(path, entry_type=ArtifactState, metadata={"v": "1"}).record(
            "a", ArtifactState(hash="1")
        )
        assert StateStore(path, entry_type=ArtifactState).metadata == {"v": "1"}

    def test_metadata_without_a_file_is_the_configured_value(self, tmp_path):
        store = StateStore(
            tmp_path / "state.json", entry_type=ArtifactState, metadata={"v": "1"}
        )
        assert store.metadata == {"v": "1"}

    def test_no_metadata_key_when_none_is_configured(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record("a", ArtifactState(hash="1"))
        assert "metadata" not in json.loads((tmp_path / "state.json").read_text())

    def test_invalid_metadata_raises(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text('{"schema_version": "1", "entries": {}, "metadata": []}')
        with pytest.raises(AppException):
            StateStore(path, entry_type=ArtifactState).metadata


class TestReplaceAll:
    def test_drops_entries_that_are_no_longer_produced(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record_many({"a": ArtifactState(hash="1"), "b": ArtifactState(hash="2")})
        store.replace_all({"b": ArtifactState(hash="3")})
        assert set(store.load()) == {"b"}
        assert store.load()["b"].hash == "3"

    def test_empty_mapping_clears_the_file(self, tmp_path):
        store = StateStore(tmp_path / "state.json", entry_type=ArtifactState)
        store.record("a", ArtifactState(hash="1"))
        store.replace_all({})
        assert store.load() == {}


class TestRender:
    def test_output_is_canonical_regardless_of_insertion_order(self):
        first = StateStore.render({"b": 1, "a": {"z": 1, "y": 2}})
        second = StateStore.render({"a": {"y": 2, "z": 1}, "b": 1})
        assert first == second
        assert first.endswith("\n")
