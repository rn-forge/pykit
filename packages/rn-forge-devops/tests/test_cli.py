"""Tests for the `rn-forge-devops` console script."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rn_forge.devops import cli


def test_cli_requirements_prints_each_problem_and_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["pkgs/*"]\n'
    )
    for name, deps in (("a", ""), ("b", 'dependencies = ["a>=1"]\n')):
        (tmp_path / "pkgs" / name).mkdir(parents=True)
        (tmp_path / "pkgs" / name / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "1.0"\n{deps}'
        )
    monkeypatch.chdir(tmp_path)
    assert cli.main(["requirements"]) == 1
    assert capsys.readouterr().err == "b: a>=1 has no ceiling\n"


def _releases(tmp_path: Path) -> Path:
    page = tmp_path / "releases" / "release-6" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "# Release 6 — kit\n\n| **Status** | shipped |\n\n## Shipped\n\nDone.\n",
        encoding="utf-8",
    )
    return page.parent.parent


def test_umbrella_writes_body_and_prints_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    body = tmp_path / "body.md"
    monkeypatch.setattr("sys.stdin", io.StringIO("abc\trefs/tags/pkg-v1.0.0\n"))
    args = ["umbrella", str(_releases(tmp_path)), str(body), "--site-url", "https://x/"]
    assert cli.main(args) == 0
    assert capsys.readouterr().out == "tag=release-6\ntitle=Release 6 — kit\n"
    assert body.read_text(encoding="utf-8") == (
        "Done.\n\nRelease page: https://x/releases/release-6/\n"
    )


def test_umbrella_prints_nothing_when_tag_listed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    body = tmp_path / "body.md"
    monkeypatch.setattr("sys.stdin", io.StringIO("abc\trefs/tags/release-6\n"))
    args = ["umbrella", str(_releases(tmp_path)), str(body), "--site-url", "https://x/"]
    assert cli.main(args) == 0
    assert capsys.readouterr().out == ""
    assert not body.exists()


def test_umbrella_refuses_a_releases_dir_outside_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    releases = _releases(tmp_path)
    body = tmp_path / "body.md"
    monkeypatch.chdir(work)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    args = ["umbrella", str(releases), str(body), "--site-url", "https://x/"]
    assert cli.main(args) == 1
    assert "outside the working directory" in capsys.readouterr().err
    assert not body.exists()


def test_umbrella_refuses_a_body_file_outside_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    releases = _releases(work)
    body = tmp_path / "body.md"
    monkeypatch.chdir(work)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    args = ["umbrella", str(releases), str(body), "--site-url", "https://x/"]
    assert cli.main(args) == 1
    assert "outside the working directory" in capsys.readouterr().err
    assert not body.exists()
