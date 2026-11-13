"""Tests for rn_forge.commons.fs.paths."""

from __future__ import annotations

import errno
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


class TestAtomicReplace:
    def test_publishes_edited_content(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        with PathUtils.atomic_replace(target) as tmp:
            assert tmp.parent == tmp_path
            assert tmp.name.startswith(".f.txt.")
            assert tmp.name.endswith(".tmp")
            assert tmp.read_text() == "old"
            tmp.write_text("new")
        assert target.read_text() == "new"
        assert list(tmp_path.iterdir()) == [target]

    def test_publishes_content_swapped_in_by_rename(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        with PathUtils.atomic_replace(target) as tmp:
            other = tmp_path / "other"
            other.write_text("swapped")
            os.replace(other, tmp)
        assert target.read_text() == "swapped"
        assert list(tmp_path.iterdir()) == [target]

    def test_exception_leaves_original_and_no_temporary(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        with pytest.raises(RuntimeError), PathUtils.atomic_replace(target) as tmp:
            tmp.write_text("partial")
            raise RuntimeError("boom")
        assert target.read_text() == "old"
        assert list(tmp_path.iterdir()) == [target]

    def test_keyboard_interrupt_leaves_original(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        with pytest.raises(KeyboardInterrupt), PathUtils.atomic_replace(target):
            raise KeyboardInterrupt
        assert target.read_text() == "old"
        assert list(tmp_path.iterdir()) == [target]

    def test_cleanup_tolerates_temporary_moved_away(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        with pytest.raises(RuntimeError), PathUtils.atomic_replace(target) as tmp:
            tmp.unlink()
            raise RuntimeError("boom")
        assert list(tmp_path.iterdir()) == [target]

    def test_keeps_original_mode(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        os.chmod(target, 0o640)
        with PathUtils.atomic_replace(target, copy=False) as tmp:
            tmp.write_text("new")
        assert (target.stat().st_mode & 0o777) == 0o640

    def test_replaces_a_read_only_file(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        os.chmod(target, 0o440)
        with PathUtils.atomic_replace(target) as tmp:
            other = tmp_path / "other"
            other.write_text("new")
            os.chmod(other, 0o440)
            os.replace(other, tmp)
        assert target.read_text() == "new"
        assert (target.stat().st_mode & 0o777) == 0o440

    def test_explicit_mode_wins(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("old")
        os.chmod(target, 0o600)
        with PathUtils.atomic_replace(target, mode=0o644) as tmp:
            tmp.write_text("new")
        assert (target.stat().st_mode & 0o777) == 0o644

    def test_copy_of_missing_path_raises_and_leaves_no_temporary(self, tmp_path):
        with (
            pytest.raises(FileNotFoundError),
            PathUtils.atomic_replace(tmp_path / "missing.txt"),
        ):
            pytest.fail("body must not run")
        assert list(tmp_path.iterdir()) == []

    def test_no_copy_creates_missing_path(self, tmp_path):
        target = tmp_path / "new.txt"
        with PathUtils.atomic_replace(target, copy=False) as tmp:
            assert tmp.read_text() == ""
            tmp.write_text("fresh")
        assert target.read_text() == "fresh"


class TestMoveNoClobber:
    def test_moves_file(self, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text("data")
        dst = tmp_path / "d.txt"
        assert PathUtils.move_no_clobber(src, dst) == dst
        assert dst.read_text() == "data"
        assert not src.exists()

    def test_existing_destination_refused_and_both_kept(self, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text("src")
        dst = tmp_path / "d.txt"
        dst.write_text("dst")
        with pytest.raises(FileExistsError):
            PathUtils.move_no_clobber(src, dst)
        assert src.read_text() == "src"
        assert dst.read_text() == "dst"

    def test_destination_created_after_call_starts_is_kept(self, tmp_path, monkeypatch):
        src = tmp_path / "s.txt"
        src.write_text("src")
        dst = tmp_path / "d.txt"
        real_link = os.link

        def racing_link(a, b, *args, **kwargs):
            Path(b).write_text("raced")
            return real_link(a, b, *args, **kwargs)

        monkeypatch.setattr(os, "link", racing_link)
        with pytest.raises(FileExistsError):
            PathUtils.move_no_clobber(src, dst)
        assert dst.read_text() == "raced"
        assert src.read_text() == "src"

    def test_same_path_keeps_file(self, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text("data")
        with pytest.raises(FileExistsError):
            PathUtils.move_no_clobber(src, src)
        assert src.read_text() == "data"

    def test_creates_missing_parents(self, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text("data")
        dst = tmp_path / "a" / "b" / "d.txt"
        PathUtils.move_no_clobber(src, dst)
        assert dst.read_text() == "data"

    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PathUtils.move_no_clobber(tmp_path / "nope", tmp_path / "d.txt")

    @pytest.mark.skipif(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        reason="permission checks do not apply to root",
    )
    def test_read_only_parent_raises(self, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text("data")
        locked = tmp_path / "locked"
        locked.mkdir()
        os.chmod(locked, 0o500)
        try:
            with pytest.raises(PermissionError):
                PathUtils.move_no_clobber(src, locked / "d.txt")
        finally:
            os.chmod(locked, 0o700)
        assert src.read_text() == "data"

    def _exdev_once(self, monkeypatch):
        real_link = os.link
        calls: list[int] = []

        def link(a, b, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise OSError(errno.EXDEV, "cross-device")
            return real_link(a, b, *args, **kwargs)

        monkeypatch.setattr(os, "link", link)

    def test_moves_across_devices(self, tmp_path, monkeypatch):
        src = tmp_path / "s.txt"
        src.write_text("data")
        os.chmod(src, 0o400)
        dst = tmp_path / "out" / "d.txt"
        self._exdev_once(monkeypatch)
        PathUtils.move_no_clobber(src, dst)
        assert dst.read_text() == "data"
        assert not src.exists()
        assert [p.name for p in dst.parent.iterdir()] == ["d.txt"]

    def test_cross_device_existing_destination_leaves_everything(
        self, tmp_path, monkeypatch
    ):
        src = tmp_path / "s.txt"
        src.write_text("src")
        dst = tmp_path / "d.txt"
        dst.write_text("dst")
        self._exdev_once(monkeypatch)
        with pytest.raises(FileExistsError):
            PathUtils.move_no_clobber(src, dst)
        assert src.read_text() == "src"
        assert dst.read_text() == "dst"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["d.txt", "s.txt"]

    def test_other_oserror_propagates(self, tmp_path, monkeypatch):
        src = tmp_path / "s.txt"
        src.write_text("data")

        def link(*args, **kwargs):
            raise OSError(errno.EPERM, "no hard links")

        monkeypatch.setattr(os, "link", link)
        with pytest.raises(OSError) as info:
            PathUtils.move_no_clobber(src, tmp_path / "d.txt")
        assert info.value.errno == errno.EPERM
        assert src.read_text() == "data"


class TestPruneEmptyParents:
    def test_removes_chain_up_to_stop(self, tmp_path):
        leaf = tmp_path / "lib" / "a" / "b"
        leaf.mkdir(parents=True)
        PathUtils.prune_empty_parents(leaf, tmp_path / "lib")
        assert (tmp_path / "lib").is_dir()
        assert list((tmp_path / "lib").iterdir()) == []

    def test_stops_at_non_empty_directory(self, tmp_path):
        leaf = tmp_path / "lib" / "a" / "b" / "c"
        leaf.mkdir(parents=True)
        keep = tmp_path / "lib" / "a" / "keep.txt"
        keep.write_text("x")
        PathUtils.prune_empty_parents(leaf, tmp_path / "lib")
        assert keep.read_text() == "x"
        assert not (tmp_path / "lib" / "a" / "b").exists()

    def test_never_removes_stop(self, tmp_path):
        stop = tmp_path / "lib"
        stop.mkdir()
        PathUtils.prune_empty_parents(stop, stop)
        assert stop.is_dir()

    def test_start_outside_stop_does_nothing(self, tmp_path):
        stop = tmp_path / "lib"
        stop.mkdir()
        outside = tmp_path / "other" / "x"
        outside.mkdir(parents=True)
        PathUtils.prune_empty_parents(outside, stop)
        assert outside.is_dir()

    def test_sibling_with_shared_prefix_is_outside(self, tmp_path):
        stop = tmp_path / "lib"
        stop.mkdir()
        sibling = tmp_path / "lib2" / "x"
        sibling.mkdir(parents=True)
        PathUtils.prune_empty_parents(sibling, stop)
        assert sibling.is_dir()

    def test_symlink_resolving_outside_stop_does_nothing(self, tmp_path):
        stop = tmp_path / "lib"
        stop.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = stop / "link"
        link.symlink_to(outside, target_is_directory=True)
        PathUtils.prune_empty_parents(link, stop)
        assert outside.is_dir()
        assert link.is_symlink()

    def test_missing_start_continues_to_parent(self, tmp_path):
        stop = tmp_path / "lib"
        (stop / "a").mkdir(parents=True)
        PathUtils.prune_empty_parents(stop / "a" / "gone", stop)
        assert not (stop / "a").exists()
        assert stop.is_dir()

    def test_file_start_raises_and_is_kept(self, tmp_path):
        stop = tmp_path / "lib"
        stop.mkdir()
        f = stop / "f.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            PathUtils.prune_empty_parents(f, stop)
        assert f.read_text() == "x"

    @pytest.mark.skipif(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        reason="permission checks do not apply to root",
    )
    def test_permission_error_propagates(self, tmp_path):
        stop = tmp_path / "lib"
        (stop / "a").mkdir(parents=True)
        os.chmod(stop, 0o500)
        try:
            with pytest.raises(PermissionError):
                PathUtils.prune_empty_parents(stop / "a", stop)
        finally:
            os.chmod(stop, 0o700)


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
