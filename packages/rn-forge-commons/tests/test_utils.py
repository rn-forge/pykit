"""Tests for rn_forge.commons.utils."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from rn_forge.commons.utils import AppUtils, Base64, Environment, PathUtils


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class TestEnvironment:
    def test_get_all_returns_dict(self):
        result = Environment.get_all()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_existing(self, monkeypatch):
        monkeypatch.setenv("_TEST_VAR", "hello")
        assert Environment.get("_TEST_VAR") == "hello"

    def test_get_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("_MISSING_VAR", raising=False)
        assert Environment.get("_MISSING_VAR") is None

    def test_get_missing_with_default(self, monkeypatch):
        monkeypatch.delenv("_MISSING_VAR", raising=False)
        assert Environment.get("_MISSING_VAR", "fallback") == "fallback"

    def test_set_returns_value(self, monkeypatch):
        monkeypatch.delenv("_SET_VAR", raising=False)
        result = Environment.set("_SET_VAR", "world")
        assert result == "world"
        assert os.environ["_SET_VAR"] == "world"

    def test_is_enabled_true_tokens(self, monkeypatch):
        for token in ("true", "True", "TRUE", "yes", "YES", "enabled", "ENABLED"):
            monkeypatch.setenv("_FLAG", token)
            assert Environment.is_enabled("_FLAG") is True, token

    def test_is_enabled_false_tokens(self, monkeypatch):
        for token in ("false", "False", "no", "NO", "disabled", "none", "None"):
            monkeypatch.setenv("_FLAG", token)
            assert Environment.is_enabled("_FLAG") is False, token

    def test_is_enabled_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("_FLAG", raising=False)
        assert Environment.is_enabled("_FLAG") is False
        assert Environment.is_enabled("_FLAG", default=True) is True

    def test_is_enabled_unrecognised_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("_FLAG", "maybe")
        assert Environment.is_enabled("_FLAG") is False
        assert Environment.is_enabled("_FLAG", default=True) is True


# ---------------------------------------------------------------------------
# Base64
# ---------------------------------------------------------------------------


class TestBase64:
    def test_encode_string(self):
        assert Base64.encode("hello") == "aGVsbG8="

    def test_encode_bytes(self):
        assert Base64.encode(b"hello") == "aGVsbG8="

    def test_decode_to_bytes(self):
        assert Base64.decode("aGVsbG8=") == b"hello"

    def test_decode_bytes_input(self):
        assert Base64.decode(b"aGVsbG8=") == b"hello"

    def test_decode_to_string(self):
        assert Base64.decode_to_string("aGVsbG8=") == "hello"

    def test_round_trip(self):
        original = "The quick brown fox"
        assert Base64.decode_to_string(Base64.encode(original)) == original

    def test_round_trip_bytes(self):
        data = b"\x00\x01\x02\xff"
        assert Base64.decode(Base64.encode(data)) == data


# ---------------------------------------------------------------------------
# PathUtils
# ---------------------------------------------------------------------------


class TestPathUtils:
    def test_temp_dir_is_path(self):
        td = PathUtils.temp_dir()
        assert isinstance(td, Path)
        assert td.exists()

    def test_write_file_text(self, tmp_path):
        p = PathUtils.write_file("hello world", tmp_path / "out.txt")
        assert p.read_text() == "hello world"

    def test_write_file_creates_parents(self, tmp_path):
        p = PathUtils.write_file("data", tmp_path / "a" / "b" / "c.txt")
        assert p.exists()
        assert p.read_text() == "data"

    def test_write_file_bytes(self, tmp_path):
        data = b"\x00\xff"
        p = PathUtils.write_file(data, tmp_path / "bin.dat")
        assert p.read_bytes() == data

    def test_write_file_returns_path(self, tmp_path):
        result = PathUtils.write_file("x", tmp_path / "f.txt")
        assert isinstance(result, Path)

    def test_delete_file(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("bye")
        PathUtils.delete(f)
        assert not f.exists()

    def test_delete_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "file.txt").write_text("hi")
        PathUtils.delete(d)
        assert not d.exists()

    def test_delete_missing_ignore(self, tmp_path):
        PathUtils.delete(tmp_path / "nonexistent")  # no error

    def test_delete_missing_strict(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PathUtils.delete(tmp_path / "nonexistent", ignore_missing=False)

    def test_delete_symlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hi")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        PathUtils.delete(link)
        assert not link.exists()
        assert target.exists()


# ---------------------------------------------------------------------------
# AppUtils.parse_bool
# ---------------------------------------------------------------------------


class TestParseBool:
    @pytest.mark.parametrize("value", [True, False])
    def test_passthrough_bool(self, value):
        assert AppUtils.parse_bool(value) is value

    @pytest.mark.parametrize("s", ["true", "True", "TRUE"])
    def test_truthy_true(self, s):
        assert AppUtils.parse_bool(s) is True

    @pytest.mark.parametrize("s", ["yes", "YES", "enabled", "ENABLED"])
    def test_truthy_other(self, s):
        assert AppUtils.parse_bool(s) is True

    @pytest.mark.parametrize("s", ["false", "False", "FALSE"])
    def test_falsy_false(self, s):
        assert AppUtils.parse_bool(s) is False

    @pytest.mark.parametrize("s", ["no", "NO", "disabled", "none", "None"])
    def test_falsy_other(self, s):
        assert AppUtils.parse_bool(s) is False

    def test_unrecognised_strict_raises(self):
        with pytest.raises(ValueError):
            AppUtils.parse_bool("maybe")

    def test_unrecognised_non_strict_returns_none(self):
        assert AppUtils.parse_bool("maybe", strict=False) is None

    def test_strips_whitespace(self):
        assert AppUtils.parse_bool(" true ") is True
        assert AppUtils.parse_bool(" none ") is False


# ---------------------------------------------------------------------------
# AppUtils.is_empty
# ---------------------------------------------------------------------------


class TestIsEmpty:
    def test_none(self):
        assert AppUtils.is_empty(None) is True

    def test_zero_not_empty(self):
        assert AppUtils.is_empty(0) is False

    def test_false_not_empty(self):
        assert AppUtils.is_empty(False) is False

    def test_negative_not_empty(self):
        assert AppUtils.is_empty(-1) is False

    def test_blank_string(self):
        assert AppUtils.is_empty("") is True
        assert AppUtils.is_empty("   ") is True

    def test_nonempty_string(self):
        assert AppUtils.is_empty("x") is False

    def test_empty_list(self):
        assert AppUtils.is_empty([]) is True

    def test_nonempty_list(self):
        assert AppUtils.is_empty([1]) is False

    def test_empty_dict(self):
        assert AppUtils.is_empty({}) is True

    def test_nonempty_dict(self):
        assert AppUtils.is_empty({"a": 1}) is False

    def test_empty_tuple(self):
        assert AppUtils.is_empty(()) is True

    def test_nonempty_tuple(self):
        assert AppUtils.is_empty((1,)) is False

    def test_falsey_object_uses_bool_fallback(self):
        class Falsey:
            def __bool__(self):
                return False

        assert AppUtils.is_empty(Falsey()) is True


# ---------------------------------------------------------------------------
# AppUtils.get_or_default
# ---------------------------------------------------------------------------


class TestGetOrDefault:
    def test_returns_value_when_present(self):
        assert AppUtils.get_or_default("hello") == "hello"

    def test_returns_default_for_none(self):
        assert AppUtils.get_or_default(None, "fallback") == "fallback"

    def test_returns_default_for_blank_string(self):
        assert AppUtils.get_or_default("  ", "fallback") == "fallback"

    def test_returns_default_for_empty_list(self):
        assert AppUtils.get_or_default([], [1, 2]) == [1, 2]

    def test_default_is_none_when_unspecified(self):
        assert AppUtils.get_or_default(None) is None

    def test_zero_is_not_empty(self):
        assert AppUtils.get_or_default(0, 99) == 0

    def test_false_is_not_empty(self):
        assert AppUtils.get_or_default(False, True) is False


# ---------------------------------------------------------------------------
# AppUtils.import_string
# ---------------------------------------------------------------------------


class TestImportString:
    def test_import_stdlib_function(self):
        join = AppUtils.import_string("os.path.join")
        import os.path

        assert join is os.path.join

    def test_import_class(self):
        imported_path = AppUtils.import_string("pathlib.Path")
        assert imported_path is Path

    def test_invalid_qualname_raises(self):
        with pytest.raises(ImportError):
            AppUtils.import_string("no_dots_here")

    def test_missing_attribute_raises(self):
        with pytest.raises(ImportError):
            AppUtils.import_string("os.path.nonexistent_function_xyz")

    def test_relative_without_package_raises(self):
        with pytest.raises(ImportError):
            AppUtils.import_string(".submodule.Foo")

    def test_missing_module_raises(self):
        with pytest.raises(ImportError):
            AppUtils.import_string("totally_missing_module_xyz.Symbol")


# Coverage ROI notes:
# - Import-string failure cases are covered at the wrapper level; importer and
#   logging internals are delegated to Python's import machinery.


# ---------------------------------------------------------------------------
# AppUtils.null_safe_attrgetter
# ---------------------------------------------------------------------------


@dataclass
class _Inner:
    value: int


@dataclass
class _Outer:
    inner: _Inner | None


class TestNullSafeAttrgetter:
    def test_resolves_nested_attribute(self):
        obj = _Outer(inner=_Inner(value=42))
        getter = AppUtils.null_safe_attrgetter("inner.value")
        assert getter(obj) == 42

    def test_returns_default_on_missing_attr(self):
        obj = _Outer(inner=None)
        getter = AppUtils.null_safe_attrgetter("inner.value", default=-1)
        assert getter(obj) == -1

    def test_default_is_none_by_default(self):
        obj = _Outer(inner=None)
        getter = AppUtils.null_safe_attrgetter("inner.value")
        assert getter(obj) is None

    def test_multiple_paths_returns_list(self):
        @dataclass
        class Point:
            x: int
            y: int

        p = Point(x=1, y=2)
        getter = AppUtils.null_safe_attrgetter("x", "y")
        assert getter(p) == [1, 2]

    def test_multiple_paths_missing_returns_default(self):
        obj = _Outer(inner=None)
        getter = AppUtils.null_safe_attrgetter(
            "inner.value", "inner.missing", default=[]
        )
        assert getter(obj) == []


# ---------------------------------------------------------------------------
# AppUtils.join_string
# ---------------------------------------------------------------------------


class TestJoinString:
    def test_basic_join(self):
        assert AppUtils.join_string(", ", "a", "b", "c") == "a, b, c"

    def test_single_value(self):
        assert AppUtils.join_string("-", "only") == "only"

    def test_empty_returns_empty_string(self):
        assert AppUtils.join_string(",") == ""

    def test_converts_non_strings(self):
        assert AppUtils.join_string("|", 1, 2, 3) == "1|2|3"

    def test_unpacks_single_list(self):
        assert AppUtils.join_string(", ", ["x", "y", "z"]) == "x, y, z"

    def test_unpacks_single_tuple(self):
        assert AppUtils.join_string("-", (1, 2, 3)) == "1-2-3"

    def test_does_not_unpack_string(self):
        # A bare string should NOT be iterated character-by-character
        assert AppUtils.join_string(",", "abc") == "abc"

    def test_multiple_lists_not_unpacked(self):
        # Two list args: each list is stringified, not unpacked
        result = AppUtils.join_string("|", [1, 2], [3, 4])
        assert result == "[1, 2]|[3, 4]"
