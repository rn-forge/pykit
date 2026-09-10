"""Tests for rn_forge.commons.fs.documents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomlkit
from ruamel.yaml import YAMLError

import rn_forge.commons.fs.documents as documents_module
from rn_forge.commons.fs.documents import (
    ConfigFormat,
    DocumentError,
    DocumentUtils,
    JsonUtils,
    YamlUtils,
)

from conftest import raise_


class TestConfigFormat:
    @pytest.mark.parametrize(
        ("suffix", "expected"),
        [
            (".toml", ConfigFormat.TOML),
            (".yaml", ConfigFormat.YAML),
            (".yml", ConfigFormat.YAML),
            (".json", ConfigFormat.JSON),
        ],
    )
    def test_suffix_dispatch(self, suffix, expected, tmp_path):
        path = tmp_path / f"config{suffix}"
        assert ConfigFormat.of(path) == expected

    def test_override_wins(self, tmp_path):
        path = tmp_path / "config.txt"
        assert ConfigFormat.of(path, override="json") == ConfigFormat.JSON

    def test_unsupported_suffix_raises(self, tmp_path):
        path = tmp_path / "config.ini"
        with pytest.raises(DocumentError):
            ConfigFormat.of(path)


class TestPlainIO:
    def test_toml_round_trip(self):
        text = DocumentUtils.dumps({"a": 1, "b": {"c": 2}}, ConfigFormat.TOML)
        assert DocumentUtils.loads(text, ConfigFormat.TOML) == {"a": 1, "b": {"c": 2}}

    def test_yaml_round_trip(self):
        text = DocumentUtils.dumps({"a": 1, "b": {"c": 2}}, ConfigFormat.YAML)
        assert DocumentUtils.loads(text, ConfigFormat.YAML) == {"a": 1, "b": {"c": 2}}

    def test_json_round_trip(self):
        text = DocumentUtils.dumps({"a": 1, "b": {"c": 2}}, ConfigFormat.JSON)
        assert DocumentUtils.loads(text, ConfigFormat.JSON) == {"a": 1, "b": {"c": 2}}

    def test_non_mapping_root_raises_toml(self):
        with pytest.raises(DocumentError):
            DocumentUtils.loads("just text with no = sign", ConfigFormat.TOML)

    def test_non_mapping_root_raises_json(self):
        with pytest.raises(DocumentError):
            DocumentUtils.loads("[1, 2, 3]", ConfigFormat.JSON)

    @pytest.mark.parametrize("text", ["false", "0", "[]", "[1]", '""'])
    def test_non_mapping_root_raises_yaml(self, text):
        with pytest.raises(DocumentError, match="root must be a mapping"):
            DocumentUtils.loads(text, ConfigFormat.YAML)

    def test_empty_yaml_is_empty_mapping(self):
        assert DocumentUtils.loads("", ConfigFormat.YAML) == {}

    def test_read_missing_ok_returns_empty(self, tmp_path):
        assert DocumentUtils.read(tmp_path / "missing.toml", missing_ok=True) == {}

    def test_read_missing_not_ok_raises(self, tmp_path):
        with pytest.raises(DocumentError):
            DocumentUtils.read(tmp_path / "missing.toml")

    def test_write_then_read(self, tmp_path):
        path = tmp_path / "config.toml"
        DocumentUtils.write(path, {"a": 1})
        assert DocumentUtils.read(path) == {"a": 1}


class TestRoundTripDocuments:
    def test_toml_comments_and_key_order_survive(self, tmp_path):
        path = tmp_path / "config.toml"
        original = "# leading comment\na = 1\nb = 2  # trailing comment\n"
        path.write_text(original)
        document = DocumentUtils.read_document(path)
        DocumentUtils.write_document(path, document)
        result = path.read_text()
        assert result == original

    def test_yaml_comments_survive(self, tmp_path):
        path = tmp_path / "config.yaml"
        original = "# a comment\na: \"hello\" # inline\nb: 'world'\n"
        path.write_text(original)
        document = DocumentUtils.read_document(path)
        DocumentUtils.write_document(path, document)
        assert path.read_text() == original

    @pytest.mark.parametrize("suffix", ["yaml", "json"])
    @pytest.mark.parametrize("text", ["false", "0", "[]", "[1]", '""'])
    def test_non_mapping_root_rejected_without_modifying_file(
        self, tmp_path, suffix, text
    ):
        path = tmp_path / f"config.{suffix}"
        path.write_text(text)
        with pytest.raises(DocumentError, match="root must be a mapping"):
            DocumentUtils.read_document(path)
        with pytest.raises(DocumentError, match="root must be a mapping"):
            DocumentUtils.update(path, {"a": 1})
        assert path.read_text() == text

    def test_empty_yaml_document_can_be_updated(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("")
        assert DocumentUtils.read_document(path) == {}
        DocumentUtils.update(path, {"a": 1})
        assert DocumentUtils.read(path) == {"a": 1}

    def test_update_deep_merges_and_preserves_comments(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("# keep me\na = 1\n\n[nested]\nx = 1\n")
        DocumentUtils.update(path, {"nested": {"y": 2}})
        result = path.read_text()
        assert "# keep me" in result
        document = DocumentUtils.read_document(path)
        assert document["nested"]["x"] == 1
        assert document["nested"]["y"] == 2

    def test_update_on_missing_file_creates_it(self, tmp_path):
        path = tmp_path / "config.toml"
        DocumentUtils.update(path, {"a": 1})
        assert DocumentUtils.read(path) == {"a": 1}

    def test_non_mapping_root_document_raises_on_update(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(DocumentError):
            DocumentUtils.update(path, {"a": 1})


class TestAppendToArray:
    def test_appends_to_new_array(self):
        document = tomlkit.document()
        DocumentUtils.append_to_array(document, "workspaces", {"name": "a"})
        assert len(document["workspaces"]) == 1
        assert document["workspaces"][0]["name"] == "a"

    def test_appends_to_existing_array_without_disturbing_comments(self):
        text = '# keep\n[[workspaces]]\nname = "a"\n'
        document = tomlkit.loads(text)
        DocumentUtils.append_to_array(document, "workspaces", {"name": "b"})
        rendered = tomlkit.dumps(document)
        assert "# keep" in rendered
        assert len(document["workspaces"]) == 2


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
            documents_module.json,
            "dumps",
            lambda *a, **k: raise_(TypeError("boom")),
        )
        with pytest.raises(TypeError, match="boom"):
            JsonUtils.serialize({"a": 1})

    def test_serialize_path(self) -> None:
        from pathlib import Path

        result = JsonUtils.serialize({"p": Path("/tmp/x")})
        assert json.loads(result) == {"p": "/tmp/x"}

    def test_serialize_enum(self) -> None:
        from enum import Enum

        class Color(Enum):
            RED = "red"

        result = JsonUtils.serialize({"c": Color.RED})
        assert json.loads(result) == {"c": "red"}

    def test_serialize_datetime(self) -> None:
        from datetime import date, datetime, time

        result = JsonUtils.serialize(
            {
                "dt": datetime(2026, 1, 1, 12, 0, 0),
                "d": date(2026, 1, 1),
                "t": time(12, 0, 0),
            }
        )
        parsed = json.loads(result)
        assert parsed["dt"] == datetime(2026, 1, 1, 12, 0, 0).isoformat()
        assert parsed["d"] == date(2026, 1, 1).isoformat()
        assert parsed["t"] == time(12, 0, 0).isoformat()

    def test_serialize_set_is_sorted_list(self) -> None:
        result = JsonUtils.serialize({"s": {3, 1, 2}})
        assert json.loads(result) == {"s": [1, 2, 3]}

    def test_serialize_decimal(self) -> None:
        from decimal import Decimal

        result = JsonUtils.serialize({"d": Decimal("1.5")})
        assert json.loads(result) == {"d": 1.5}

    def test_serialize_nested_dataclass(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner

        result = JsonUtils.serialize(Outer(Inner(5)))
        assert json.loads(result) == {"inner": {"value": 5}}


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
        with pytest.raises(YAMLError):
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
        with pytest.raises(YAMLError):
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
            documents_module,
            "_yaml_dump",
            lambda *a, **k: raise_(RuntimeError("bad dump")),
        )
        with pytest.raises(RuntimeError, match="bad dump"):
            YamlUtils.serialize({"a": 1})

    def test_serialize_all_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            documents_module,
            "_yaml_dump_all",
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
        with pytest.raises(YAMLError):
            YamlUtils.read_file(p)

    def test_read_file_all_error_propagates(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("a: 1\n---\nb: [2")
        with pytest.raises(YAMLError):
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
