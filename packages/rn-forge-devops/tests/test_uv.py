"""Tests for the uv workspace adapter's manifest reading."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from rn_forge.devops import Package, Smoke, Workspace, uv


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
        '[tool.workspace-ci.postgres]\nenv = "DSN"\n\n'
        '[tool.workspace-ci.redis]\nenv = "URL"\n',
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
    assert app.redis_env == "URL"
    assert workspace.pytest_args == ["-m", "not slow"]


def _adapter_member(root: Path, adapters: str, extras: str, files: list[str]) -> None:
    _write(
        root / "pyproject.toml",
        '[tool.uv.workspace]\nmembers = ["pkgs/*"]\n',
    )
    _write(
        root / "pkgs/data/pyproject.toml",
        '[project]\nname = "data"\nversion = "1"\n\n'
        f"[project.optional-dependencies]\n{extras}\n\n"
        f"[tool.workspace-ci]\n{adapters}\n",
    )
    for file in files:
        _write(root / "pkgs/data/src/data" / file, "")


def test_check_adapters_passes_for_modules_and_subpackages(tmp_path: Path) -> None:
    _adapter_member(
        tmp_path,
        'adapters = ["pandas", "oidc"]',
        "pandas = []\noidc = []",
        ["pandas.py", "oidc/__init__.py", "core.py"],
    )
    assert uv.check_adapters(uv.load_workspace(tmp_path)) == []


def test_check_adapters_reports_a_missing_module(tmp_path: Path) -> None:
    _adapter_member(tmp_path, 'adapters = ["pandas"]', "pandas = []", ["core.py"])
    assert uv.check_adapters(uv.load_workspace(tmp_path)) == [
        "data: adapter pandas has no module pandas"
    ]


def test_check_adapters_reports_a_missing_extra(tmp_path: Path) -> None:
    _adapter_member(tmp_path, 'adapters = ["pandas"]', "excel = []", ["pandas.py"])
    assert uv.check_adapters(uv.load_workspace(tmp_path)) == [
        "data: adapter pandas has no extra pandas"
    ]


def test_check_adapters_reports_a_duplicate(tmp_path: Path) -> None:
    _adapter_member(
        tmp_path, 'adapters = ["pandas", "pandas"]', "pandas = []", ["pandas.py"]
    )
    assert uv.check_adapters(uv.load_workspace(tmp_path)) == [
        "data: adapter pandas is declared twice"
    ]


def test_check_adapters_skips_a_member_without_the_key(tmp_path: Path) -> None:
    _workspace(tmp_path)
    assert uv.check_adapters(uv.load_workspace(tmp_path)) == []


def _stub_uv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace `subprocess.run` so `uv build` writes a wheel and nothing else runs."""
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:2] == ["uv", "build"]:
            name = command[command.index("--package") + 1]
            out = Path(command[command.index("--out-dir") + 1])
            out.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(out / f"{name}-1-py3-none-any.whl", "w") as wheel:
                wheel.writestr(f"{name}-1.dist-info/METADATA", f"Name: {name}\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(uv.subprocess, "run", run)
    return calls


def test_smoke_without_a_declaration_imports_the_package_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_uv(monkeypatch)
    package = Package("app", "pkgs/app", "app_core")
    workspace = Workspace(root=tmp_path, packages={"app": package})
    assert uv.smoke(workspace, "app", "") == 0
    builds = [c for c in calls if c[:2] == ["uv", "build"]]
    assert [c[c.index("--package") + 1] for c in builds] == ["app"]
    assert any("--no-deps" in c for c in calls)
    assert calls[-1][-1] == "app_core"
    assert calls[-1][-2] == ""


def test_smoke_with_a_declaration_imports_its_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_uv(monkeypatch)
    package = Package("app", "pkgs/app", "app", smoke=Smoke(modules=["app.core"]))
    workspace = Workspace(root=tmp_path, packages={"app": package})
    assert uv.smoke(workspace, "app", "") == 0
    assert calls[-1][-1] == "app.core"
