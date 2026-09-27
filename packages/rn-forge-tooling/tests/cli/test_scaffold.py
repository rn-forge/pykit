"""A tool with a declared lifecycle, installed from built wheels."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

PYPROJECT = """\
[project]
name = "golden-tool"
version = "1.0.0"
requires-python = ">=3.14"
dependencies = ["rn-forge-tooling"]

[project.scripts]
golden-tool = "golden_tool.cli:app"

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"
"""

CLI_TOML = """\
[cli]
name = "golden-tool"
help = "A tool that manages its own install."

[lifecycle]
product = "golden_tool.product:PRODUCT"
"""

CLI_PY = """\
from pathlib import Path

from rn_forge.tooling.cli.lifecycle import build_tool_app

app = build_tool_app(Path(__file__).parent / "cli.toml")
"""

# Releases are archives in the directory $GOLDEN_RELEASES, with the newest version named in `latest`.
PRODUCT_PY = """\
import os
import shutil
from pathlib import Path

from rn_forge.tooling.install import Link, ToolProduct


class DirectoryReleases:
    def _root(self) -> Path:
        return Path(os.environ["GOLDEN_RELEASES"])

    def latest(self) -> str:
        return (self._root() / "latest").read_text().strip()

    def download(self, version: str, destination: Path) -> Path:
        return Path(shutil.copy(self._root() / f"golden-tool-{version}.tar.gz", destination))

    def checksum(self, version: str) -> None:
        return None


class GoldenTool(ToolProduct):
    def artifacts(self):
        return (Link("bin/golden-tool", "bin/golden-tool"),)


PRODUCT = GoldenTool(name="golden-tool", version="1.0.0", release_source=DirectoryReleases())
"""


def _release(releases: Path, version: str) -> None:
    payload = b"#!/bin/sh\necho golden-tool\n"
    with tarfile.open(releases / f"golden-tool-{version}.tar.gz", "w:gz") as tar:
        info = tarfile.TarInfo(f"golden-tool-{version}/bin/golden-tool")
        info.size = len(payload)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(payload))


@pytest.fixture
def golden_tool(scaffold_venv, tmp_path: Path):
    project = tmp_path / "golden-tool"
    package = project / "src" / "golden_tool"
    package.mkdir(parents=True)
    (project / "pyproject.toml").write_text(PYPROJECT)
    (package / "__init__.py").write_text("")
    (package / "cli.toml").write_text(CLI_TOML)
    (package / "cli.py").write_text(CLI_PY)
    (package / "product.py").write_text(PRODUCT_PY)
    script = (
        scaffold_venv(
            "rn-forge-commons", "rn-forge-cli", "rn-forge-tooling", str(project)
        )
        / "golden-tool"
    )

    home = tmp_path / "rnf-home"
    releases = tmp_path / "releases"
    releases.mkdir()
    for version in ("1.0.0", "2.0.0"):
        _release(releases, version)
    env = {**os.environ, "RNF_HOME": str(home), "GOLDEN_RELEASES": str(releases)}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(script), *args], capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    return run, home, releases


@pytest.mark.scaffold
def test_the_lifecycle_leaves_the_documented_layout(golden_tool):
    run, home, releases = golden_tool
    tool = home / "golden-tool"

    (releases / "latest").write_text("1.0.0")
    run("install")
    assert (tool / "versions" / "1.0.0" / "bin" / "golden-tool").is_file()
    assert (tool / "current").readlink() == Path("versions/1.0.0")
    assert json.loads((tool / "state.json").read_text())["version"] == "1.0.0"
    link = home / "bin" / "golden-tool"
    assert link.is_symlink()
    assert link.resolve() == (tool / "versions" / "1.0.0" / "bin" / "golden-tool").resolve()

    status = json.loads(run("--json", "status").stdout)
    assert status["installed"] == "1.0.0"

    (releases / "latest").write_text("2.0.0")
    run("upgrade")
    assert (tool / "current").readlink() == Path("versions/2.0.0")
    assert (tool / "versions" / "1.0.0").is_dir()
    assert link.resolve() == (tool / "versions" / "2.0.0" / "bin" / "golden-tool").resolve()
    assert json.loads(run("--json", "status").stdout)["installed"] == "2.0.0"

    run("uninstall", "--yes")
    assert not tool.exists()
    assert not link.is_symlink()
