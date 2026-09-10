"""Tests for rn_forge.commons.utils."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.utils import (
    AppUtils,
    Base64,
    Environment,
    PathUtils,
)


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


class TestEnvironmentRequire:
    def test_all_present_returns_mapping(self, monkeypatch):
        monkeypatch.setenv("_REQ_A", "1")
        monkeypatch.setenv("_REQ_B", "2")
        assert Environment.require("_REQ_A", "_REQ_B") == {"_REQ_A": "1", "_REQ_B": "2"}

    def test_one_missing_raises(self, monkeypatch):
        monkeypatch.setenv("_REQ_A", "1")
        monkeypatch.delenv("_REQ_MISSING", raising=False)
        with pytest.raises(AppException):
            Environment.require("_REQ_A", "_REQ_MISSING")

    def test_several_missing_all_appear_in_one_message(self, monkeypatch):
        monkeypatch.delenv("_REQ_M1", raising=False)
        monkeypatch.delenv("_REQ_M2", raising=False)
        with pytest.raises(AppException) as exc_info:
            Environment.require("_REQ_M1", "_REQ_M2")
        assert "_REQ_M1" in str(exc_info.value)
        assert "_REQ_M2" in str(exc_info.value)

    def test_empty_string_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("_REQ_EMPTY", "   ")
        with pytest.raises(AppException):
            Environment.require("_REQ_EMPTY")


class TestEnvironmentForbid:
    def test_matches_raises(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "change-me")
        with pytest.raises(AppException):
            Environment.forbid("_SECRET", "change-me")

    def test_does_not_match_passes(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "a-real-secret")
        Environment.forbid("_SECRET", "change-me")

    def test_custom_message_used(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "change-me")
        with pytest.raises(AppException, match="custom message"):
            Environment.forbid("_SECRET", "change-me", message="custom message")


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


class TestAtomicWrite:
    def test_writes_bytes(self, tmp_path):
        target = tmp_path / "f.bin"
        result = PathUtils.atomic_write(b"\x00\x01data", target)
        assert result == target
        assert target.read_bytes() == b"\x00\x01data"

    def test_writes_str(self, tmp_path):
        target = tmp_path / "f.txt"
        PathUtils.atomic_write("hello", target)
        assert target.read_text() == "hello"

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "a" / "b" / "f.txt"
        PathUtils.atomic_write("hi", target)
        assert target.read_text() == "hi"

    def test_preserves_existing_file_mode(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        os.chmod(target, 0o600)
        PathUtils.atomic_write("new", target)
        assert target.read_text() == "new"
        assert (target.stat().st_mode & 0o777) == 0o600

    def test_explicit_mode_applied(self, tmp_path):
        target = tmp_path / "f.txt"
        PathUtils.atomic_write("hi", target, mode=0o640)
        assert (target.stat().st_mode & 0o777) == 0o640

    def test_no_tmp_leftovers_after_mid_write_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "f.txt"

        def fail_fsync(fd):
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "fsync", fail_fsync)
        with pytest.raises(OSError):
            PathUtils.atomic_write("hi", target)
        assert list(tmp_path.iterdir()) == []

    def test_no_tmp_leftovers_after_keyboard_interrupt(self, tmp_path, monkeypatch):
        target = tmp_path / "f.txt"

        def raise_interrupt(fd):
            raise KeyboardInterrupt

        monkeypatch.setattr(os, "fsync", raise_interrupt)
        with pytest.raises(KeyboardInterrupt):
            PathUtils.atomic_write("hi", target)
        assert list(tmp_path.iterdir()) == []

    def test_parent_directory_fsync_failure_is_swallowed(self, tmp_path, monkeypatch):
        target = tmp_path / "f.txt"
        real_open = os.open

        def fail_dir_open(path, flags, *args, **kwargs):
            if path == tmp_path:
                raise OSError("cannot open directory")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", fail_dir_open)
        result = PathUtils.atomic_write("hi", target)  # must not raise
        assert result.read_text() == "hi"


class TestFindRoot:
    def test_marker_precedence_order(self, tmp_path):
        # .git several levels up beats pyproject.toml one level up
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        (nested.parent / "pyproject.toml").touch()
        result = PathUtils.find_root(nested, markers=(".git", "pyproject.toml"))
        assert result == tmp_path

    def test_fallback_start(self, tmp_path):
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        result = PathUtils.find_root(isolated, markers=(".nonexistent-marker",))
        assert result == isolated

    def test_fallback_raise(self, tmp_path):
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        with pytest.raises(AppException):
            PathUtils.find_root(
                isolated, markers=(".nonexistent-marker",), fallback="raise"
            )

    def test_finds_marker_at_start(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert PathUtils.find_root(tmp_path, markers=(".git",)) == tmp_path


class TestNormalizeRelative:
    def test_dot_accepted_as_root(self):
        assert PathUtils.normalize_relative(".") == "."

    def test_normal_relative_path(self):
        assert PathUtils.normalize_relative("a/b/c") == "a/b/c"

    def test_absolute_path_rejected(self):
        with pytest.raises(AppException):
            PathUtils.normalize_relative("/etc/passwd")

    def test_dotdot_escape_rejected(self):
        with pytest.raises(AppException):
            PathUtils.normalize_relative("../../etc/passwd")

    def test_empty_rejected(self):
        with pytest.raises(AppException):
            PathUtils.normalize_relative("")

    def test_internal_dotdot_resolved(self):
        assert PathUtils.normalize_relative("a/b/../c") == "a/c"


class TestAssertWithin:
    def test_path_inside_root_allowed(self, tmp_path):
        target = tmp_path / "a" / "b.txt"
        target.parent.mkdir()
        target.touch()
        assert PathUtils.assert_within(tmp_path, target) == target.resolve()

    def test_non_symlink_path_outside_root_rejected(self, tmp_path):
        outside = tmp_path.parent / f"outside-{tmp_path.name}"
        with pytest.raises(AppException):
            PathUtils.assert_within(tmp_path, outside)

    def test_symlink_resolving_inside_root_allowed(self, tmp_path):
        real = tmp_path / "real.txt"
        real.touch()
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        assert PathUtils.assert_within(tmp_path, link) == real.resolve()

    def test_symlink_resolving_outside_root_rejected(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside.txt"
        outside.touch()
        link = root / "escape.txt"
        link.symlink_to(outside)
        with pytest.raises(AppException):
            PathUtils.assert_within(root, link)

    def test_root_itself_allowed(self, tmp_path):
        assert PathUtils.assert_within(tmp_path, tmp_path) == tmp_path.resolve()


class TestPathUtilsBackup:
    def test_not_a_file_returns_none(self, tmp_path):
        assert PathUtils.backup(tmp_path / "missing.txt", tmp_path / "backups") is None

    def test_copies_file_with_relative_to(self, tmp_path):
        source_root = tmp_path / "repo"
        (source_root / "sub").mkdir(parents=True)
        source = source_root / "sub" / "f.txt"
        source.write_text("hi")
        dest_root = tmp_path / "backups"
        result = PathUtils.backup(source, dest_root, relative_to=source_root)
        assert result == dest_root / "sub" / "f.txt"
        assert result.read_text() == "hi"

    def test_copies_file_without_relative_to(self, tmp_path):
        source = tmp_path / "f.txt"
        source.write_text("hi")
        dest_root = tmp_path / "backups"
        result = PathUtils.backup(source, dest_root)
        assert result is not None
        assert result.read_text() == "hi"
        assert result.is_relative_to(dest_root)


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

    @pytest.mark.parametrize(
        "s", ["yes", "YES", "enabled", "ENABLED", "y", "Y", "on", "ON", "1"]
    )
    def test_truthy_other(self, s):
        assert AppUtils.parse_bool(s) is True

    @pytest.mark.parametrize("s", ["false", "False", "FALSE"])
    def test_falsy_false(self, s):
        assert AppUtils.parse_bool(s) is False

    @pytest.mark.parametrize(
        "s", ["no", "NO", "disabled", "none", "None", "n", "N", "off", "OFF", "0"]
    )
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

    def test_colon_separated_form_supported(self):
        join = AppUtils.import_string("os.path:join")
        import os.path

        assert join is os.path.join


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


class TestUnifiedDiff:
    def test_equal_inputs_return_empty_string(self):
        assert AppUtils.unified_diff("same\n", "same\n") == ""

    def test_different_inputs_produce_a_diff(self):
        result = AppUtils.unified_diff("a\n", "b\n")
        assert result != ""
        assert "-a" in result
        assert "+b" in result

    def test_names_appear_in_header(self):
        result = AppUtils.unified_diff(
            "a\n", "b\n", expected_name="old.txt", actual_name="new.txt"
        )
        assert "old.txt" in result
        assert "new.txt" in result
