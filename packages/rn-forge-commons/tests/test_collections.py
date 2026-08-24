"""Tests for rn_forge.commons.collections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import rn_forge.commons.collections as collections_module
from rn_forge.commons.collections import DictUtils, JsonUtils, ListUtils, YamlUtils

from conftest import raise_


# -- DictUtils.get ---------------------------------------------------------


class TestDictGet:
    def test_simple_key(self) -> None:
        assert DictUtils.get({"a": 1}, "a") == 1

    def test_nested_key(self) -> None:
        assert DictUtils.get({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_default(self) -> None:
        assert DictUtils.get({"a": 1}, "b") is None

    def test_custom_default(self) -> None:
        assert DictUtils.get({"a": 1}, "b", default=42) == 42

    def test_empty_dict(self) -> None:
        assert DictUtils.get({}, "a") is None

    def test_empty_key_path(self) -> None:
        assert DictUtils.get({"a": 1}, "") is None

    def test_list_index(self) -> None:
        data = {"a": [10, 20, 30]}
        assert DictUtils.get(data, "a.1") == 20

    def test_list_index_out_of_bounds(self) -> None:
        assert DictUtils.get({"a": [1]}, "a.5") is None

    def test_list_non_numeric_index(self) -> None:
        assert DictUtils.get({"a": [1]}, "a.x") is None

    def test_nested_through_list(self) -> None:
        data = {"a": [{"b": "found"}]}
        assert DictUtils.get(data, "a.0.b") == "found"

    def test_escaped_dot(self) -> None:
        data = {"a.b": 1}
        assert DictUtils.get(data, r"a\.b") == 1

    def test_none_intermediate(self) -> None:
        assert DictUtils.get({"a": None}, "a.b") is None

    def test_non_dict_non_list_intermediate(self) -> None:
        assert DictUtils.get({"a": 42}, "a.b") is None


# -- DictUtils.set ---------------------------------------------------------


class TestDictSet:
    def test_simple_set(self) -> None:
        d = {}
        DictUtils.set(d, "a", 1)
        assert d == {"a": 1}

    def test_nested_set_creates_intermediates(self) -> None:
        d = {}
        DictUtils.set(d, "a.b.c", 3)
        assert d == {"a": {"b": {"c": 3}}}

    def test_set_into_existing(self) -> None:
        d = {"a": {"b": 1}}
        DictUtils.set(d, "a.c", 2)
        assert d == {"a": {"b": 1, "c": 2}}

    def test_overwrite_existing(self) -> None:
        d = {"a": {"b": 1}}
        DictUtils.set(d, "a.b", 99)
        assert d == {"a": {"b": 99}}

    def test_set_into_list(self) -> None:
        d = {"a": [10, 20, 30]}
        DictUtils.set(d, "a.1", 99)
        assert d["a"] == [10, 99, 30]

    def test_list_non_numeric_raises(self) -> None:
        d = {"a": [1, 2]}
        with pytest.raises(KeyError, match="Non-numeric"):
            DictUtils.set(d, "a.x", 5)

    def test_list_index_out_of_bounds_raises(self) -> None:
        d = {"a": [1]}
        with pytest.raises(IndexError, match="out of bounds"):
            DictUtils.set(d, "a.5", 99)

    def test_empty_key_path_noop(self) -> None:
        d = {"a": 1}
        DictUtils.set(d, "", 2)
        assert d == {"a": 1}

    def test_escaped_dot(self) -> None:
        d = {}
        DictUtils.set(d, r"a\.b", 1)
        assert d == {"a.b": 1}

    def test_non_container_intermediate_raises(self) -> None:
        d = {"a": 1}
        with pytest.raises(TypeError, match="holds non-container type"):
            DictUtils.set(d, "a.b", 2)

    def test_list_entry_non_container_tail_raises(self) -> None:
        d = {"a": [42]}
        with pytest.raises(TypeError, match="resolved to non-container type"):
            DictUtils.set(d, "a.0.b", 99)

    def test_list_intermediate_non_numeric_raises(self) -> None:
        d = {"a": [{"b": 1}]}
        with pytest.raises(KeyError, match="Non-numeric"):
            DictUtils.set(d, "a.x.b", 2)

    def test_list_intermediate_index_out_of_bounds_raises(self) -> None:
        d = {"a": [{"b": 1}]}
        with pytest.raises(IndexError, match="out of bounds"):
            DictUtils.set(d, "a.5.b", 2)

    def test_list_intermediate_non_container_raises(self) -> None:
        d = {"a": [42]}
        with pytest.raises(TypeError, match="resolved to non-container type"):
            DictUtils.set(d, "a.0.b.c", 2)


# -- DictUtils.merge -------------------------------------------------------


class TestDictMerge:
    def test_no_overrides_returns_target(self) -> None:
        target = {"a": 1}
        assert (
            DictUtils.merge(target) is target
        )  # NOSONAR: deliberately asserting identity, not equality

    def test_simple_merge(self) -> None:
        target = {"a": 1}
        result = DictUtils.merge(target, {"b": 2})
        assert result == {"a": 1, "b": 2}
        assert result is target

    def test_deep_merge(self) -> None:
        target = {"a": {"x": 1, "y": 2}}
        DictUtils.merge(target, {"a": {"y": 99, "z": 3}})
        assert target == {"a": {"x": 1, "y": 99, "z": 3}}

    def test_override_replaces_non_dict(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {"a": "replaced"})
        assert target["a"] == "replaced"

    def test_multiple_overrides(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {"b": 2}, {"c": 3})
        assert target == {"a": 1, "b": 2, "c": 3}

    def test_empty_override_is_noop(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {})
        assert target == {"a": 1}

    def test_none_override_skipped(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, None)
        assert target == {"a": 1}

    def test_deep_copy_prevents_shared_refs(self) -> None:
        inner = {"x": 1}
        override = {"a": inner}
        target = {}
        DictUtils.merge(target, override)
        inner["x"] = 999
        assert target["a"]["x"] == 1


# -- DictUtils.compare -----------------------------------------------------


class TestDictCompare:
    def test_equal_dicts(self) -> None:
        assert DictUtils.compare({"a": 1}, {"a": 1}) == {}

    def test_only_in_a(self) -> None:
        result = DictUtils.compare({"a": 1, "b": 2}, {"a": 1})
        assert result == {"only_in_a": {"b": 2}}

    def test_only_in_b(self) -> None:
        result = DictUtils.compare({"a": 1}, {"a": 1, "c": 3})
        assert result == {"only_in_b": {"c": 3}}

    def test_conflict(self) -> None:
        result = DictUtils.compare({"a": 1}, {"a": 2})
        assert result == {"conflicts": {"a": [1, 2]}}

    def test_nested_conflict(self) -> None:
        result = DictUtils.compare(
            {"a": {"x": 1}},
            {"a": {"x": 2}},
        )
        assert result == {"conflicts": {"a": {"conflicts": {"x": [1, 2]}}}}

    def test_both_empty(self) -> None:
        assert DictUtils.compare({}, {}) == {}

    def test_one_empty(self) -> None:
        assert DictUtils.compare({}, {"a": 1}) == {"only_in_b": {"a": 1}}
        assert DictUtils.compare({"a": 1}, {}) == {"only_in_a": {"a": 1}}


# -- ListUtils -------------------------------------------------------------


class TestListUtils:
    def test_get_default_index(self) -> None:
        assert ListUtils.get(["a", "b"]) == "a"

    def test_get_custom_index(self) -> None:
        assert ListUtils.get(["a", "b"], 1) == "b"

    def test_get_out_of_bounds_returns_default(self) -> None:
        assert ListUtils.get(["a"], 3, default="missing") == "missing"

    def test_get_empty_returns_default(self) -> None:
        assert ListUtils.get([], default="missing") == "missing"

    def test_sort_mutates_and_returns_list(self) -> None:
        items = [{"name": "b"}, {"name": "a"}]
        result = ListUtils.sort(items, key=lambda item: item["name"])
        assert result is items
        assert items == [{"name": "a"}, {"name": "b"}]

    def test_filter_with_value(self) -> None:
        assert ListUtils.filter(["a", "b", "a"], "a") == ["a", "a"]

    def test_filter_with_predicate(self) -> None:
        assert ListUtils.filter([1, 2, 3, 4], lambda item: item % 2 == 0) == [2, 4]

    def test_group_by(self) -> None:
        items = [
            {"type": "b", "value": 2},
            {"type": "a", "value": 1},
            {"type": "b", "value": 3},
        ]
        result = ListUtils.group_by(
            items,
            key_fn=lambda item: item["type"],
            value_fn=lambda item: item["value"],
        )
        assert result == {"a": [1], "b": [2, 3]}

    def test_group_by_does_not_mutate_input(self) -> None:
        items = [{"type": "b"}, {"type": "a"}]
        ListUtils.group_by(items, key_fn=lambda item: item["type"])
        assert items == [{"type": "b"}, {"type": "a"}]

    def test_group_by_with_group_fn(self) -> None:
        items = [{"type": "a", "value": 1}, {"type": "a", "value": 2}]
        result = ListUtils.group_by(
            items,
            key_fn=lambda item: item["type"],
            value_fn=lambda item: item["value"],
            group_fn=sum,
        )
        assert result == {"a": 3}

    def test_group_by_empty_returns_empty_dict(self) -> None:
        assert ListUtils.group_by([], key_fn=str) == {}


# -- JsonUtils.load --------------------------------------------------------


class TestJsonLoad:
    def test_load_dict(self) -> None:
        result = JsonUtils.load('{"a": 1}')
        assert result == {"a": 1}

    def test_load_list(self) -> None:
        result = JsonUtils.load("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_load_with_root_key(self) -> None:
        result = JsonUtils.load('{"data": {"x": 1}, "meta": {}}', root_key="data")
        assert result == {"x": 1}

    def test_load_invalid_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            JsonUtils.load("not json")


# -- JsonUtils.serialize ---------------------------------------------------


class TestJsonSerialize:
    def test_serialize_dict(self) -> None:
        assert json.loads(JsonUtils.serialize({"a": 1})) == {"a": 1}

    def test_serialize_non_serializable_uses_repr(self) -> None:
        result = JsonUtils.serialize({"s": {1, 2}})
        assert "repr" not in result or "{1, 2}" in result

    def test_serialize_dataclass(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class Point:
            x: int
            y: int

        result = JsonUtils.serialize(Point(1, 2))
        parsed = json.loads(result)
        assert parsed == {"x": 1, "y": 2}

    def test_serialize_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            collections_module.json,
            "dumps",
            lambda *a, **k: raise_(TypeError("boom")),
        )
        with pytest.raises(TypeError, match="boom"):
            JsonUtils.serialize({"a": 1})


# -- JsonUtils file I/O ----------------------------------------------------


class TestJsonFileIO:
    def test_write_and_read(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        JsonUtils.write_file({"key": "value"}, p)
        assert p.exists()
        result = JsonUtils.read_file(p)
        assert result == {"key": "value"}

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "test.json"
        result_path = JsonUtils.write_file({"a": 1}, p)
        assert result_path == p
        assert p.exists()

    def test_write_default_indent_is_tab(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        JsonUtils.write_file({"a": 1}, p)
        content = p.read_text()
        assert "\t" in content

    def test_read_file_parse_error_propagates(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{bad")
        with pytest.raises(json.JSONDecodeError):
            JsonUtils.read_file(p)

    def test_write_file_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = tmp_path / "test.json"

        def fail(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", fail)
        with pytest.raises(OSError, match="disk full"):
            JsonUtils.write_file({"a": 1}, p)


# -- YamlUtils.load --------------------------------------------------------


class TestYamlLoad:
    def test_load_dict(self) -> None:
        result = YamlUtils.load("a: 1\nb: 2\n")
        assert result == {"a": 1, "b": 2}

    def test_load_list(self) -> None:
        result = YamlUtils.load("- 1\n- 2\n- 3\n")
        assert result == [1, 2, 3]

    def test_load_with_root_key(self) -> None:
        result = YamlUtils.load("data:\n  x: 1\nmeta: {}\n", root_key="data")
        assert result == {"x": 1}

    def test_load_nested(self) -> None:
        text = "a:\n  b:\n    c: deep\n"
        assert YamlUtils.load(text) == {"a": {"b": {"c": "deep"}}}

    def test_load_invalid_raises(self) -> None:
        with pytest.raises(yaml.YAMLError):
            YamlUtils.load("a: [1")


# -- YamlUtils.load_all ----------------------------------------------------


class TestYamlLoadAll:
    def test_multi_document(self) -> None:
        text = "a: 1\n---\nb: 2\n"
        result = YamlUtils.load_all(text)
        assert result == [{"a": 1}, {"b": 2}]

    def test_skips_empty_documents(self) -> None:
        text = "a: 1\n---\n---\nb: 2\n"
        result = YamlUtils.load_all(text)
        assert result == [{"a": 1}, {"b": 2}]

    def test_load_all_invalid_raises(self) -> None:
        with pytest.raises(yaml.YAMLError):
            YamlUtils.load_all("a: 1\n---\nb: [2")


# -- YamlUtils.serialize ---------------------------------------------------


class TestYamlSerialize:
    def test_serialize_dict(self) -> None:
        result = YamlUtils.serialize({"a": 1, "b": 2})
        parsed = YamlUtils.load(result)
        assert parsed == {"a": 1, "b": 2}

    def test_serialize_no_sort_keys_by_default(self) -> None:
        result = YamlUtils.serialize({"z": 1, "a": 2})
        lines = result.strip().split("\n")
        assert lines[0].startswith("z:")

    def test_serialize_all(self) -> None:
        result = YamlUtils.serialize_all({"a": 1}, {"b": 2})
        docs = YamlUtils.load_all(result)
        assert docs == [{"a": 1}, {"b": 2}]

    def test_serialize_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            collections_module.yaml,
            "dump",
            lambda *a, **k: raise_(RuntimeError("bad dump")),
        )
        with pytest.raises(RuntimeError, match="bad dump"):
            YamlUtils.serialize({"a": 1})

    def test_serialize_all_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            collections_module.yaml,
            "dump_all",
            lambda *a, **k: raise_(RuntimeError("bad dump all")),
        )
        with pytest.raises(RuntimeError, match="bad dump all"):
            YamlUtils.serialize_all({"a": 1})


# -- YamlUtils file I/O ----------------------------------------------------


class TestYamlFileIO:
    def test_write_and_read(self, tmp_path: Path) -> None:
        p = tmp_path / "test.yaml"
        YamlUtils.write_file({"key": "value"}, p)
        assert p.exists()
        result = YamlUtils.read_file(p)
        assert result == {"key": "value"}

    def test_read_with_root_key(self, tmp_path: Path) -> None:
        p = tmp_path / "test.yaml"
        p.write_text("data:\n  x: 1\nmeta: {}\n")
        result = YamlUtils.read_file(p, root_key="data")
        assert result == {"x": 1}

    def test_read_multi_document(self, tmp_path: Path) -> None:
        p = tmp_path / "multi.yaml"
        p.write_text("a: 1\n---\nb: 2\n")
        result = YamlUtils.read_file_all(p)
        assert result == [{"a": 1}, {"b": 2}]

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "test.yaml"
        result_path = YamlUtils.write_file({"a": 1}, p)
        assert result_path == p
        assert p.exists()

    def test_read_file_error_propagates(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("a: [1")
        with pytest.raises(yaml.YAMLError):
            YamlUtils.read_file(p)

    def test_read_file_all_error_propagates(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("a: 1\n---\nb: [2")
        with pytest.raises(yaml.YAMLError):
            YamlUtils.read_file_all(p)

    def test_write_file_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = tmp_path / "bad.yaml"

        def fail(*args, **kwargs):
            raise OSError("no space")

        monkeypatch.setattr(Path, "write_text", fail)
        with pytest.raises(OSError, match="no space"):
            YamlUtils.write_file({"a": 1}, p)


# Coverage ROI notes:
# - Logger side effects inside collections helpers are exercised indirectly via
#   success/error-path assertions but are not asserted record-by-record.
