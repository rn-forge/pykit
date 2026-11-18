"""Tests for workspace requirement checks."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from rn_forge.devops import requirements


def _workspace(
    root: Path,
    dependencies: tuple[str, ...] = (),
    *,
    version: str | None = "1.0",
    extra: str = "",
    exclude: tuple[str, ...] = (),
) -> Path:
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["pkgs/*", "missing/*"]\n'
        f"exclude = {json.dumps(list(exclude))}\n"
    )
    for name in ("a", "b"):
        path = root / "pkgs" / name / "pyproject.toml"
        path.parent.mkdir(parents=True)
        text = f'[project]\nname = "{name}"\n'
        if version is not None:
            text += f"version = {json.dumps(version)}\n"
        if name == "b":
            text += f"dependencies = {json.dumps(list(dependencies))}\n{extra}"
        path.write_text(text)
    return root


def test_each_member_manifest_is_read_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path)
    reads: Counter[Path] = Counter()
    read_text = Path.read_text

    def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
        reads[path] += 1
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)
    assert requirements.check_requirements(root) == []
    for path in root.glob("pkgs/*/pyproject.toml"):
        assert reads[path] == 1


def test_name_canonicalization_matches_member(tmp_path: Path) -> None:
    root = _workspace(tmp_path, ("Rn_Forge.A>=1",))
    path = root / "pkgs/a/pyproject.toml"
    path.write_text(path.read_text().replace('name = "a"', 'name = "rn-forge-a"'))
    assert requirements.check_requirements(root) == ["b: Rn_Forge.A>=1 has no ceiling"]


def test_extras_and_ranges_pass(tmp_path: Path) -> None:
    assert requirements.check_requirements(_workspace(tmp_path, ("a[x]>=1,<2",))) == []


def test_range_excluding_member_version(tmp_path: Path) -> None:
    assert requirements.check_requirements(_workspace(tmp_path, ("a>=2,<3",))) == [
        "b: a<3,>=2 excludes the workspace's 1.0"
    ]


def test_direct_url_reported(tmp_path: Path) -> None:
    assert requirements.check_requirements(
        _workspace(tmp_path, ("a @ https://x/a.whl",))
    ) == ["b: a is a URL; use a range (ADR-0004)"]


def test_optional_and_group_requirements_checked(tmp_path: Path) -> None:
    root = _workspace(
        tmp_path,
        extra='[project.optional-dependencies]\nx = ["a>=1"]\n'
        '[dependency-groups]\ndev = ["a>=2,<3", {include-group = "other"}]\n',
    )
    assert requirements.check_requirements(root) == [
        "b: a>=1 has no ceiling",
        "b: a<3,>=2 excludes the workspace's 1.0",
    ]


def test_marker_is_ignored(tmp_path: Path) -> None:
    root = _workspace(tmp_path, ("a>=1; python_version<'3'",))
    assert requirements.check_requirements(root) == ["b: a>=1 has no ceiling"]


def test_tilde_and_pin_have_no_ceiling(tmp_path: Path) -> None:
    root = _workspace(tmp_path, ("a~=1.0", "a==1.0"))
    assert requirements.check_requirements(root) == [
        "b: a~=1.0 has no ceiling",
        "b: a==1.0 has no ceiling",
    ]


def test_non_member_and_excluded_member_ignored(tmp_path: Path) -> None:
    root = _workspace(tmp_path, ("external>=1", "a>=1", "b>=1"), exclude=("pkgs/a",))
    assert requirements.check_requirements(root) == []


def test_member_without_version_skips_version_check(tmp_path: Path) -> None:
    root = _workspace(tmp_path, ("a>=2,<3", "a>=2"), version=None)
    assert requirements.check_requirements(root) == ["b: a>=2 has no ceiling"]


def test_malformed_requirement_raises_invalid_manifest(tmp_path: Path) -> None:
    text = "a>=>1"
    root = _workspace(tmp_path, (text,))
    with pytest.raises(requirements.InvalidManifest) as caught:
        requirements.check_requirements(root)
    assert str(root / "pkgs/b/pyproject.toml") in str(caught.value)
    assert text in str(caught.value)


def test_manifest_without_project_raises_invalid_manifest(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    path = root / "pkgs/a/pyproject.toml"
    path.write_text("[tool.other]\n")
    with pytest.raises(requirements.InvalidManifest) as caught:
        requirements.check_requirements(root)
    assert str(path) in str(caught.value)
    assert "project" in str(caught.value)
