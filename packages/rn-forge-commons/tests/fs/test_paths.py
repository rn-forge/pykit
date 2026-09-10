"""Tests for rn_forge.commons.fs.paths."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.paths import PathUtils


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
