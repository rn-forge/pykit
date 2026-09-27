"""Fixtures for scaffold tests: applications installed from wheels built from this checkout."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
Installer = Callable[..., Path]


@pytest.fixture(scope="session")
def built_wheels(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Wheels of every workspace package, built once per session, keyed by package name."""
    out = tmp_path_factory.mktemp("wheels")
    wheels: dict[str, Path] = {}
    for package in sorted((ROOT / "packages").glob("rn-forge-*")):
        subprocess.run(
            [
                "uv",
                "build",
                "--package",
                package.name,
                "--wheel",
                "--out-dir",
                str(out),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    for wheel in out.glob("rn_forge_*.whl"):
        wheels[wheel.name.split("-")[0].replace("_", "-")] = wheel
    return wheels


@pytest.fixture
def scaffold_venv(built_wheels: dict[str, Path], tmp_path: Path) -> Installer:
    """Return ``install(*requirements)``, which makes a clean venv and returns its ``bin`` dir.

    A requirement naming a workspace package (``rn-forge-web[drf]``) is served by its built wheel;
    anything else resolves from the index. Extras named here apply to the served wheel; the override
    replaces a sibling's git pin whole, so an extra it needs is named here too.
    """

    def install(*requirements: str) -> Path:
        venv = tmp_path / "venv"
        wanted = dict(_split(requirement) for requirement in requirements)
        # The wheels pin their siblings as git URLs; overriding them with the local wheels
        # keeps every install offline from the repository.
        overrides = tmp_path / "overrides.txt"
        overrides.write_text(
            "".join(
                f"{name}{wanted.get(name, '')} @ {wheel.as_uri()}\n"
                for name, wheel in built_wheels.items()
            )
        )
        subprocess.run(["uv", "venv", "-q", "-p", "3.14", str(venv)], check=True)
        resolved = [
            requirement
            for requirement in requirements
            if _split(requirement)[0] not in built_wheels
        ] + [name for name in wanted if name in built_wheels]
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "-q",
                "--python",
                str(venv / "bin" / "python"),
                "--override",
                str(overrides),
                *resolved,
            ],
            check=True,
        )
        return venv / "bin"

    return install


def _split(requirement: str) -> tuple[str, str]:
    """``rn-forge-web[security]`` -> ``("rn-forge-web", "[security]")``."""
    name, bracket, extras = requirement.partition("[")
    return name, f"{bracket}{extras}"
