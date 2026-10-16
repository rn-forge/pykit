"""Tests for the CI core: graph ordering and release gating."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rn_forge.devops import Package, Smoke, normalize, plan, release_order, releasable
from rn_forge.devops.ci import Workspace, changed_files, select


def _packages() -> dict[str, Package]:
    return {
        "base": Package("base", "packages/base", "base"),
        "app": Package("app", "packages/app", "app", requires={"base"}),
    }


def test_normalize_collapses_separators() -> None:
    assert normalize("Rn_Forge.Devops") == "rn-forge-devops"


def test_release_order_puts_requirements_first() -> None:
    assert release_order(_packages(), {"app", "base"}) == ["base", "app"]


def test_missing_marker_blocks_package_and_dependents(tmp_path: Path) -> None:
    ok, blocked = releasable(_packages(), tmp_path, ["app", "base"])
    assert (ok, blocked) == ([], ["base", "app"])


def test_passed_markers_release_in_order(tmp_path: Path) -> None:
    for name in ("base", "app"):
        (tmp_path / f"{name}.verify").touch()
    assert releasable(_packages(), tmp_path, ["app", "base"]) == (
        ["base", "app"],
        [],
    )


def test_plan_lists_smoke_checks_per_extra(tmp_path: Path) -> None:
    packages = _packages()
    packages["app"].smoke = Smoke(modules=["app"], extras={"x": ["app.x"]})
    workspace = Workspace(root=tmp_path, packages=packages)
    outputs = plan(workspace, "")
    assert outputs["release-order"] == ["base", "app"]
    assert outputs["smoke"] == [
        {"name": "app", "extra": "", "marker": "app.smoke"},
        {"name": "app", "extra": "x", "marker": "app.smoke-x"},
    ]
    assert outputs["sonar"] is False


def _git_workspace(tmp_path: Path) -> Workspace:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("1")
    git("add", ".")
    git("commit", "-q", "-m", "one")
    git("tag", "v1")
    (tmp_path / "a" / "f.txt").write_text("2")
    git("commit", "-q", "-am", "two")
    packages = {n: Package(n, n, n) for n in ("a", "b")}
    return Workspace(root=tmp_path, packages=packages)


def test_select_uses_valid_base(tmp_path: Path) -> None:
    assert select(_git_workspace(tmp_path), "v1") == {"a"}


def test_select_rejects_option_like_base_without_running_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _git_workspace(tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("git must not run for an invalid base")

    monkeypatch.setattr(subprocess, "run", fail)
    assert select(workspace, "--output=x") == {"a", "b"}
    assert "selecting all packages" in capsys.readouterr().err


def test_changed_files_rejects_option_like_base(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid base"):
        changed_files(tmp_path, "--output=x")
