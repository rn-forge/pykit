"""A command-line application declared through rn-forge-cli, installed from built wheels."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PYPROJECT = """\
[project]
name = "golden-app"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["rn-forge-cli"]

[project.scripts]
golden-app = "golden_app.cli:app"

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"
"""

CLI_TOML = """\
[cli]
name = "golden-app"
help = "Do the thing."

[[cli.commands]]
name = "hello"
target = "golden_app.commands:hello"

[[cli.commands]]
name = "fail"
target = "golden_app.commands:fail"
"""

CLI_PY = """\
from pathlib import Path

from rn_forge.cli import CliApp

app = CliApp.from_config(Path(__file__).parent / "cli.toml")
"""

COMMANDS_PY = """\
from rn_forge.commons.exceptions import AppException


def hello() -> None:
    \"\"\"Say hello.\"\"\"
    print("hello from golden-app")


def fail() -> None:
    \"\"\"Fail with an application error.\"\"\"
    raise AppException("could not do the thing")
"""


@pytest.fixture
def golden_app(scaffold_venv, tmp_path: Path) -> Path:
    project = tmp_path / "golden-app"
    package = project / "src" / "golden_app"
    package.mkdir(parents=True)
    (project / "pyproject.toml").write_text(PYPROJECT)
    (package / "__init__.py").write_text("")
    (package / "cli.toml").write_text(CLI_TOML)
    (package / "cli.py").write_text(CLI_PY)
    (package / "commands.py").write_text(COMMANDS_PY)
    bin_dir = scaffold_venv("rn-forge-commons", "rn-forge-cli", str(project))
    return bin_dir / "golden-app"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(script), *args], capture_output=True, text=True)


@pytest.mark.scaffold
class TestGoldenApp:
    def test_runs_a_command(self, golden_app):
        result = _run(golden_app, "hello")
        assert result.returncode == 0
        assert "hello from golden-app" in result.stdout

    def test_prints_help(self, golden_app):
        result = _run(golden_app, "--help")
        assert result.returncode == 0
        assert "Do the thing." in result.stdout
        assert "hello" in result.stdout

    def test_maps_an_application_error_to_its_exit_code(self, golden_app):
        result = _run(golden_app, "fail")
        assert result.returncode == 1
        assert "could not do the thing" in result.stdout + result.stderr
