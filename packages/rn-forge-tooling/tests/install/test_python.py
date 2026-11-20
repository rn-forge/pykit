"""Tests for rn_forge.tooling.install.python."""

from __future__ import annotations

import io
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

import pytest
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.subprocess import Process
from rn_forge.tooling.install import (
    Link,
    PythonTool,
    ToolHome,
    extract_archive,
    install,
    uninstall,
)
from rn_forge.tooling.install import python as python_module

needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")

PYPROJECT = b"""\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "pytool"
version = "1.0.0"
scripts = {pytool = "pytool:main"}

[tool.setuptools]
py-modules = ["pytool"]
"""
MODULE = b'def main() -> None:\n    print("pytool ok")\n'


def make_archive(directory: Path) -> Path:
    """A release tarball of a minimal Python tool with one console script."""
    archive = directory / "pytool-1.0.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, payload in (
            ("pytool-1.0.0/pyproject.toml", PYPROJECT),
            ("pytool-1.0.0/pytool.py", MODULE),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return archive


@dataclass
class FakeSource:
    directory: Path

    def latest(self) -> str:
        return "1.0.0"

    def download(self, version: str, destination: Path) -> Path:
        return make_archive(destination)

    def checksum(self, version: str) -> str | None:
        return None


@pytest.fixture
def home(tmp_path):
    return ToolHome("pytool", tmp_path / "home")


@pytest.fixture
def tool(tmp_path):
    return PythonTool(
        name="pytool", version="1.0.0", release_source=FakeSource(tmp_path)
    )


def test_artifacts_link_the_named_command(tool):
    assert tool.artifacts() == (Link("bin/pytool", "bin/pytool"),)


def test_preflight_refuses_without_uv(tool, monkeypatch):
    monkeypatch.setattr(python_module.shutil, "which", lambda name: None)
    with pytest.raises(AppException, match="uv"):
        tool.preflight()


def test_install_without_uv_writes_nothing(tool, home, monkeypatch):
    monkeypatch.setattr(python_module.shutil, "which", lambda name: None)
    with pytest.raises(AppException, match="uv"):
        install(tool, home=home)
    assert not home.product_dir.exists()
    assert not home.versions_dir.exists()


@needs_uv
def test_build_leaves_the_command_in_the_version_directory(tool, tmp_path):
    root = extract_archive(make_archive(tmp_path), tmp_path / "extracted")
    version_dir = tmp_path / "built"
    tool.build(root, version_dir)
    assert (
        Process.execute("run", str(version_dir / "bin/pytool")).stdout == "pytool ok\n"
    )


@needs_uv
def test_an_installed_command_runs_through_current(tool, home):
    install(tool, home=home)
    assert Process.execute("run", str(home.root / "bin/pytool")).stdout == "pytool ok\n"


@needs_uv
def test_uninstall_leaves_no_file_under_the_home(tool, home):
    install(tool, home=home)
    uninstall(tool, home=home)
    # bin/ is shared by every installed product, so uninstall leaves the directory.
    assert not home.product_dir.exists()
    # env.sh belongs to the home, so uninstall leaves it.
    leftover = [p for p in home.root.rglob("*") if not p.is_dir() or p.is_symlink()]
    assert leftover == [home.env_path]
