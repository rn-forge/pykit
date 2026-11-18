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
    return subprocess.run(
        [str(script), *args], check=False, capture_output=True, text=True
    )


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


_WORKSPACE = Path(__file__).parents[3]
_WHERE = (
    "import pydantic, rn_forge.cli, rn_forge.commons;"
    "print(rn_forge.cli.__file__, rn_forge.commons.__file__, pydantic.__file__)"
)


@pytest.mark.scaffold
class TestScaffoldInstall:
    def test_one_wheel_is_built_for_every_workspace_package(self, built_wheels):
        packages = {path.name for path in (_WORKSPACE / "packages").glob("rn-forge-*")}
        assert len(packages) == 10
        assert set(built_wheels) == packages

    def test_installs_the_built_distributions_outside_the_workspace(
        self, scaffold_venv, tmp_path: Path
    ):
        bin_dir = scaffold_venv("rn-forge-commons[pydantic]", "rn-forge-cli")
        result = subprocess.run(
            [str(bin_dir / "python"), "-c", _WHERE],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        paths = [Path(item) for item in result.stdout.split()]
        assert len(paths) == 3
        for path in paths:
            assert path.is_relative_to(bin_dir.parent / "lib")
            assert not path.is_relative_to(_WORKSPACE / "packages")

    def test_an_extra_is_installed_only_when_asked_for(
        self, scaffold_venv, tmp_path: Path
    ):
        bin_dir = scaffold_venv("rn-forge-commons")
        result = subprocess.run(
            [str(bin_dir / "python"), "-c", "import pydantic"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "ModuleNotFoundError" in result.stderr
