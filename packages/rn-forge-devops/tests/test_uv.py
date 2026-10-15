"""Tests for the uv workspace adapter's manifest reading."""

from __future__ import annotations

from pathlib import Path

import pytest

from rn_forge.devops import uv


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _workspace(root: Path) -> None:
    _write(
        root / "pyproject.toml",
        '[tool.uv.workspace]\nmembers = ["pkgs/*"]\n\n'
        '[tool.workspace-ci]\npytest-args = ["-m", "not slow"]\n',
    )
    _write(
        root / "pkgs/base/pyproject.toml", '[project]\nname = "base"\nversion = "1"\n'
    )
    _write(
        root / "pkgs/app/pyproject.toml",
        '[project]\nname = "App_X"\nversion = "1"\ndependencies = ["base>=1"]\n\n'
        '[tool.workspace-ci.postgres]\nenv = "DSN"\n',
    )


def test_find_root_walks_up_from_a_subdirectory(tmp_path: Path) -> None:
    _workspace(tmp_path)
    assert uv.find_root(tmp_path / "pkgs" / "app") == tmp_path


def test_find_root_fails_outside_a_workspace(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        uv.find_root(tmp_path)


def test_load_workspace_reads_members_and_settings(tmp_path: Path) -> None:
    _workspace(tmp_path)
    workspace = uv.load_workspace(tmp_path)
    assert sorted(workspace.packages) == ["app-x", "base"]
    app = workspace.packages["app-x"]
    assert (app.dir, app.module, app.requires) == ("pkgs/app", "app_x", {"base"})
    assert app.postgres_env == "DSN"
    assert workspace.pytest_args == ["-m", "not slow"]
