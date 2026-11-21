"""Tests for rn_forge.tooling.install.python."""

from __future__ import annotations

import io
import shutil
import subprocess
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
TYPER_PYPROJECT = PYPROJECT.replace(
    b'version = "1.0.0"\n', b'version = "1.0.0"\ndependencies = ["typer==0.27.2"]\n'
)
TYPER_MODULE = b"""\
import typer

app = typer.Typer()


@app.command()
def hello() -> None:
    print("pytool ok")


@app.command()
def bye() -> None:
    print("bye")


def main() -> None:
    app()
"""


def make_archive(directory: Path, *, typer: bool = True) -> Path:
    """A release tarball of a minimal Python tool with one console script.

    The tool is a Typer app unless *typer* is false, in which case its command
    ignores the completion variable.
    """
    archive = directory / "pytool-1.0.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, payload in (
            ("pytool-1.0.0/pyproject.toml", TYPER_PYPROJECT if typer else PYPROJECT),
            ("pytool-1.0.0/pytool.py", TYPER_MODULE if typer else MODULE),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return archive


@dataclass
class FakeSource:
    directory: Path
    typer: bool = True

    def latest(self) -> str:
        return "1.0.0"

    def download(self, version: str, destination: Path) -> Path:
        return make_archive(destination, typer=self.typer)

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


def test_artifacts_link_the_command_and_its_completion(tool):
    assert tool.artifacts() == (
        Link("bin/pytool", "bin/pytool"),
        Link("completions/_pytool", "completions/_pytool"),
    )


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
        Process.execute("run", str(version_dir / "bin/pytool"), "hello").stdout
        == "pytool ok\n"
    )


@needs_uv
def test_build_writes_a_completion_script(tool, tmp_path):
    root = extract_archive(make_archive(tmp_path), tmp_path / "extracted")
    version_dir = tmp_path / "built"
    tool.build(root, version_dir)
    lines = (version_dir / "completions/_pytool").read_text().splitlines()
    assert lines[0] == "#compdef pytool"
    assert lines[-1] == '_pytool_completion "$@"'


@dataclass
class FakeResult:
    stdout: str


SCRIPT = (
    "\n#compdef my-tool\n\n_my_tool_completion() { :; }\n\n"
    "compdef _my_tool_completion my-tool\n"
)


def record_execute(monkeypatch, stdout):
    calls = []

    def execute(name, *args, **kwargs):
        calls.append((name, args, kwargs))
        return FakeResult(stdout)

    monkeypatch.setattr(python_module.Process, "execute", execute)
    return calls


def test_the_completion_variable_follows_clicks_naming(tmp_path, monkeypatch):
    tool = PythonTool(
        name="my-tool", version="1.0.0", release_source=FakeSource(tmp_path)
    )
    calls = record_execute(monkeypatch, SCRIPT)
    version_dir = tmp_path / "built"
    tool.build(tmp_path, version_dir)
    assert calls[1][2]["env"]["_MY_TOOL_COMPLETE"] == "source_zsh"
    written = (version_dir / "completions/_my-tool").read_text()
    assert written.startswith("#compdef my-tool")
    assert written.endswith('_my_tool_completion "$@"\n')


def test_a_script_without_compdef_fails_the_build(tmp_path, monkeypatch):
    tool = PythonTool(
        name="my-tool", version="1.0.0", release_source=FakeSource(tmp_path)
    )
    record_execute(monkeypatch, "\n#compdef my-tool\n\n_my_tool_completion() { :; }\n")
    with pytest.raises(AppException, match="compdef"):
        tool.build(tmp_path, tmp_path / "built")


@needs_uv
def test_a_command_that_ignores_the_variable_rolls_back(tmp_path, home):
    tool = PythonTool(
        name="pytool", version="1.0.0", release_source=FakeSource(tmp_path, typer=False)
    )
    with pytest.raises(AppException, match="completion"):
        install(tool, home=home)
    assert home.installed_versions() == []
    assert not list(home.versions_dir.glob("*"))
    assert not (home.root / "bin/pytool").is_symlink()
    assert not (home.root / "completions/_pytool").is_symlink()


@needs_uv
def test_an_installed_command_runs_through_current(tool, home):
    install(tool, home=home)
    assert (
        Process.execute("run", str(home.root / "bin/pytool"), "hello").stdout
        == "pytool ok\n"
    )


@needs_uv
def test_install_links_the_completion_through_current(tool, home):
    install(tool, home=home)
    link = home.root / "completions/_pytool"
    assert link.is_symlink()
    assert link.resolve().is_relative_to(home.current.resolve())
    uninstall(tool, home=home)
    assert not link.is_symlink()
    assert not (home.root / "bin/pytool").is_symlink()


DRIVER = """\
zmodload zsh/zpty
zpty t 'zsh -f -i'
zpty -w t 'PS1="> "; source "{home}/env.sh"; autoload -Uz compinit; compinit -u -d "{tmp}/zcompdump"; echo RE""ADY'
zpty -r -m t out '*READY*'
sleep 1; while zpty -r -t t chunk; do :; done
buf=""
for keys in $'pytool \t' $'\t'; do
  zpty -w -n t "$keys"
  sleep 2
  while zpty -r -t t chunk; do buf+=$chunk; done
done
print -r -- "$buf"
zpty -d t
"""


@needs_uv
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not on PATH")
def test_zsh_completes_the_installed_tool(tool, home, tmp_path):
    install(tool, home=home)
    driver = tmp_path / "driver.zsh"
    driver.write_text(DRIVER.format(home=home.root, tmp=tmp_path))
    result = subprocess.run(
        ["zsh", "-f", str(driver)],
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "hello" in result.stdout
    assert "bye" in result.stdout


@needs_uv
def test_uninstall_leaves_no_file_under_the_home(tool, home):
    install(tool, home=home)
    uninstall(tool, home=home)
    # bin/ is shared by every installed product, so uninstall leaves the directory.
    assert not home.product_dir.exists()
    # env.sh belongs to the home, so uninstall leaves it.
    leftover = [p for p in home.root.rglob("*") if not p.is_dir() or p.is_symlink()]
    assert leftover == [home.env_path]
