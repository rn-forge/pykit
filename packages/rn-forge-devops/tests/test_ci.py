"""Tests for the CI core: graph ordering and release gating."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from rn_forge.devops import Package, Smoke, normalize, plan, release_order, releasable
from rn_forge.devops.ci import Workspace, changed_files, select
from rn_forge.devops.requirements import check_requirements


def _packages() -> dict[str, Package]:
    return {
        "base": Package("base", "packages/base", "base"),
        "app": Package(
            "app", "packages/app", "app", requires={"base"}, release_requires={"base"}
        ),
    }


def _group_cycle() -> dict[str, Package]:
    return {
        "auth": Package(
            "auth", "auth", "auth", requires={"web"}, release_requires={"web"}
        ),
        "web": Package("web", "web", "web", requires={"auth"}),
    }


def test_normalize_collapses_separators() -> None:
    assert normalize("Rn_Forge.Devops") == "rn-forge-devops"


def test_release_order_puts_requirements_first() -> None:
    assert release_order(_packages(), {"app", "base"}) == ["base", "app"]


def test_release_order_ignores_a_cycle_through_a_dependency_group() -> None:
    assert release_order(_group_cycle(), {"auth", "web"}) == ["web", "auth"]


def test_release_order_raises_on_a_runtime_cycle() -> None:
    packages = {
        "a": Package("a", "a", "a", release_requires={"b"}),
        "b": Package("b", "b", "b", release_requires={"a"}),
    }
    with pytest.raises(ValueError, match=r"cycle among \['a', 'b'\]"):
        release_order(packages, {"a", "b"})


def test_plan_orders_a_group_only_cycle(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path, packages=_group_cycle())
    assert plan(workspace, "")["release-order"] == ["web", "auth"]


def test_releasable_gates_on_release_requires_only(tmp_path: Path) -> None:
    packages = _group_cycle()
    for check in packages["auth"].checks():
        (tmp_path / check["marker"]).touch()
    assert releasable(packages, tmp_path, ["auth", "web"]) == ([], ["web", "auth"])
    for check in packages["web"].checks():
        (tmp_path / check["marker"]).touch()
    assert releasable(packages, tmp_path, ["auth", "web"]) == (["web", "auth"], [])
    (tmp_path / packages["auth"].checks()[0]["marker"]).unlink()
    assert releasable(packages, tmp_path, ["auth", "web"]) == (["web"], ["auth"])


def test_missing_marker_blocks_package_and_dependents(tmp_path: Path) -> None:
    ok, blocked = releasable(_packages(), tmp_path, ["app", "base"])
    assert (ok, blocked) == ([], ["base", "app"])


def test_passed_markers_release_in_order(tmp_path: Path) -> None:
    for name in ("base", "app"):
        for check in Package(name, name, name).checks():
            (tmp_path / check["marker"]).touch()
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
        {"name": "base", "extra": "", "marker": "base.smoke"},
        {"name": "app", "extra": "", "marker": "app.smoke"},
        {"name": "app", "extra": "x", "marker": "app.smoke-x"},
    ]
    assert outputs["sonar"] is False


def test_plan_lists_one_empty_extra_smoke_entry_without_a_declaration(
    tmp_path: Path,
) -> None:
    outputs = plan(Workspace(root=tmp_path, packages=_packages()), "")
    assert outputs["smoke"] == [
        {"name": "base", "extra": "", "marker": "base.smoke"},
        {"name": "app", "extra": "", "marker": "app.smoke"},
    ]


def test_plan_omits_smoke_entries_of_unselected_packages(tmp_path: Path) -> None:
    outputs = plan(_git_workspace(tmp_path), "v1")
    assert outputs["smoke"] == [{"name": "a", "extra": "", "marker": "a.smoke"}]


def test_plan_lists_redis_runs_of_selected_packages(tmp_path: Path) -> None:
    packages = _packages()
    packages["app"].redis_env = "REDIS_URL"
    outputs = plan(Workspace(root=tmp_path, packages=packages), "")
    assert outputs["redis"] == [
        {"name": "app", "dir": "packages/app", "env": "REDIS_URL"}
    ]
    assert outputs["postgres"] == []


def test_checks_include_the_redis_marker_only_when_declared() -> None:
    package = Package("app", "packages/app", "app")
    assert {"kind": "redis", "marker": "app.redis"} not in package.checks()
    package.redis_env = "REDIS_URL"
    assert {"kind": "redis", "marker": "app.redis"} in package.checks()


def test_missing_redis_marker_blocks_a_package(tmp_path: Path) -> None:
    packages = _packages()
    packages["base"].redis_env = "REDIS_URL"
    for package in packages.values():
        for check in package.checks():
            if check["marker"] != "base.redis":
                (tmp_path / check["marker"]).touch()
    assert releasable(packages, tmp_path, ["base", "app"]) == ([], ["base", "app"])


def test_checks_always_include_the_smoke_marker() -> None:
    package = Package("base", "packages/base", "base")
    assert {"kind": "smoke", "extra": "", "marker": "base.smoke"} in package.checks()


def test_missing_smoke_marker_blocks_a_package_without_a_declaration(
    tmp_path: Path,
) -> None:
    packages = _packages()
    (tmp_path / "base.verify").touch()
    assert releasable(packages, tmp_path, ["base"]) == ([], ["base"])
    (tmp_path / "base.smoke").touch()
    assert releasable(packages, tmp_path, ["base"]) == (["base"], [])


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


def test_plan_outputs_match_documented_keys(tmp_path: Path) -> None:
    page = Path(__file__).parents[1] / "docs" / "reference" / "subcommands.md"
    text = page.read_text(encoding="utf-8")
    table = text.split("<!-- plan-outputs:start -->")[1].split(
        "<!-- plan-outputs:end -->"
    )[0]
    documented = set(re.findall(r"^\| `([^`]+)` \|", table, flags=re.MULTILINE))
    workspace = Workspace(tmp_path, _packages())
    assert documented == set(plan(workspace, ""))


def _members(root: Path, app_requires: str, *, group: bool = False) -> None:
    (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["pkgs/*"]\n')
    (root / "pkgs/base").mkdir(parents=True)
    (root / "pkgs/app").mkdir()
    (root / "pkgs/base/pyproject.toml").write_text(
        '[project]\nname = "rn-forge-base"\nversion = "0.7.0"\n'
    )
    table = (
        f'[dependency-groups]\ndev = ["{app_requires}"]\n'
        if group
        else f'[project.optional-dependencies]\nx = ["{app_requires}"]\n'
    )
    (root / "pkgs/app/pyproject.toml").write_text(
        '[project]\nname = "rn-forge-app"\nversion = "1.0.0"\n'
        'dependencies = ["requests>=2"]\n\n' + table
    )


def test_requirements_reports_a_url(tmp_path: Path) -> None:
    _members(tmp_path, "rn-forge-base @ git+https://example.com/x@v1")
    assert check_requirements(tmp_path) == [
        "rn-forge-app: rn-forge-base is a URL; use a range (ADR-0004)"
    ]


def test_requirements_reports_a_range_excluding_the_workspace_version(
    tmp_path: Path,
) -> None:
    _members(tmp_path, "rn-forge-base>=0.5,<0.7", group=True)
    assert check_requirements(tmp_path) == [
        "rn-forge-app: rn-forge-base<0.7,>=0.5 excludes the workspace's 0.7.0"
    ]


def test_requirements_reports_a_missing_ceiling(tmp_path: Path) -> None:
    _members(tmp_path, "rn-forge-base>=0.7.0")
    assert check_requirements(tmp_path) == [
        "rn-forge-app: rn-forge-base>=0.7.0 has no ceiling"
    ]


def test_requirements_passes_a_range_with_extras(tmp_path: Path) -> None:
    _members(tmp_path, "rn-forge-base[pydantic]>=0.7.0,<0.8")
    assert check_requirements(tmp_path) == []


def test_requirements_ignores_non_members(tmp_path: Path) -> None:
    _members(tmp_path, "requests @ https://example.com/r.whl")
    assert check_requirements(tmp_path) == []


def test_requirements_module_imports_neither_planner_nor_adapters() -> None:
    path = Path(__file__).parents[1] / "src/rn_forge/devops/requirements.py"
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('req', {str(path)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "loaded = [m for m in ('ci', 'uv', 'github')"
        " if f'rn_forge.devops.{m}' in sys.modules]\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "[]"
