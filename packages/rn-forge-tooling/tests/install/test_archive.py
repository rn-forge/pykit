"""Tests for rn_forge.tooling.install.archive."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.tooling.install import extract_archive


class TestExtractArchive:
    def test_extracts_tar_gz(self, tmp_path):
        import tarfile

        src_dir = tmp_path / "src" / "root"
        src_dir.mkdir(parents=True)
        (src_dir / "file.txt").write_text("hello")
        archive = tmp_path / "archive.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src_dir, arcname="root")

        dest = tmp_path / "extracted"
        result = extract_archive(archive, dest)
        assert result == dest / "root"
        assert (result / "file.txt").read_text() == "hello"

    def test_extracts_zip(self, tmp_path):
        import zipfile

        archive = tmp_path / "archive.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("root/file.txt", "hello")

        dest = tmp_path / "extracted"
        result = extract_archive(archive, dest)
        assert result == dest / "root"
        assert (result / "file.txt").read_text() == "hello"

    def test_multiple_root_dirs_raises(self, tmp_path):
        import zipfile

        archive = tmp_path / "archive.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("a/file.txt", "1")
            zf.writestr("b/file.txt", "2")

        dest = tmp_path / "extracted"
        with pytest.raises(AppException):
            extract_archive(archive, dest)
