"""Tests for rn_forge.commons.fs.locks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.locks import DirectoryLock, atomic_symlink


class TestAtomicSymlink:
    def test_creates_new_symlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hi")
        link = tmp_path / "link"
        atomic_symlink(link, target)
        assert link.is_symlink()
        assert link.read_text() == "hi"

    def test_replaces_existing_symlink(self, tmp_path):
        target1 = tmp_path / "t1.txt"
        target1.write_text("one")
        target2 = tmp_path / "t2.txt"
        target2.write_text("two")
        link = tmp_path / "link"
        atomic_symlink(link, target1)
        atomic_symlink(link, target2)
        assert link.read_text() == "two"

    def test_no_tmp_leftovers(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hi")
        link = tmp_path / "link"
        atomic_symlink(link, target)
        leftovers = [p for p in tmp_path.iterdir() if ".tmp-" in p.name]
        assert leftovers == []


class TestDirectoryLock:
    def test_acquires_and_releases(self, tmp_path):
        lock_path = tmp_path / ".lock"
        with DirectoryLock(lock_path):
            assert lock_path.exists()
        assert not lock_path.exists()

    def test_second_acquisition_waits_then_times_out(self, tmp_path):
        lock_path = tmp_path / ".lock"
        lock_path.mkdir()
        with pytest.raises(AppException):
            with DirectoryLock(lock_path, timeout=0.1, poll_interval=0.02):
                pass

    def test_on_wait_called_when_blocked(self, tmp_path):
        lock_path = tmp_path / ".lock"
        lock_path.mkdir()
        waited = []
        with pytest.raises(AppException):
            with DirectoryLock(
                lock_path, timeout=0.1, poll_interval=0.02, on_wait=waited.append
            ):
                pass
        assert waited == [lock_path]

    def test_lock_released_on_exception(self, tmp_path):
        lock_path = tmp_path / ".lock"
        with pytest.raises(RuntimeError):
            with DirectoryLock(lock_path):
                raise RuntimeError("boom")
        assert not lock_path.exists()
