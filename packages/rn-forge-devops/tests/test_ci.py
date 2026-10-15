"""Tests for the CI core: graph ordering and release gating."""

from __future__ import annotations

from pathlib import Path

from rn_forge.devops import Package, Smoke, normalize, plan, release_order, releasable
from rn_forge.devops.ci import Workspace


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
