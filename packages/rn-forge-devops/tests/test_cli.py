"""Tests for the `rn-forge-devops` console script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rn_forge.devops import cli
from rn_forge.devops.index import ReleaseFile


def _env(monkeypatch: pytest.MonkeyPatch, event: str, ref_type: str, name: str) -> None:
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("REF_TYPE", ref_type)
    monkeypatch.setenv("REF_NAME", name)


def test_cli_prints_branch_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "workflow_dispatch", "branch", "feature/release-2")
    monkeypatch.setattr("sys.argv", ["rn-forge-devops", "sonar-target"])
    assert cli.main() == 0
    assert capsys.readouterr().out == (
        "branch-arg=-Dsonar.branch.name=feature/release-2\n"
    )


def test_cli_prints_empty_argument_for_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "pull_request", "branch", "12/merge")
    monkeypatch.setattr("sys.argv", ["rn-forge-devops", "sonar-target"])
    assert cli.main() == 0
    assert capsys.readouterr().out == "branch-arg=\n"


def test_cli_exits_with_message_for_tag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "workflow_dispatch", "tag", "v1.0")
    monkeypatch.setattr("sys.argv", ["rn-forge-devops", "sonar-target"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert "unsupported ref" in str(exit_info.value.code)
    assert capsys.readouterr().out == ""


def _adapter_workspace(root: Path, extras: str) -> None:
    (root / "pkgs/data/src/data").mkdir(parents=True)
    (root / "pkgs/data/src/data/pandas.py").write_text("")
    (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["pkgs/*"]\n')
    (root / "pkgs/data/pyproject.toml").write_text(
        '[project]\nname = "data"\nversion = "1"\n\n'
        f"[project.optional-dependencies]\n{extras}\n\n"
        '[tool.workspace-ci]\nadapters = ["pandas"]\n'
    )


def test_cli_adapters_is_silent_when_they_are_declared_correctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _adapter_workspace(tmp_path, "pandas = []")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["adapters"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_cli_adapters_prints_each_problem_to_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _adapter_workspace(tmp_path, "excel = []")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["adapters"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "data: adapter pandas has no extra pandas\n"


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


def test_cli_index_writes_the_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = ReleaseFile("rn-forge-web", "w.whl", "https://dl/w.whl", "aa")
    monkeypatch.setattr(cli.releases, "release_files", lambda repo: [file])
    assert cli.main(["index", "--repo", "o/r", "--out", str(tmp_path / "simple")]) == 0
    assert "rn-forge-web/" in (tmp_path / "simple/index.html").read_text()
    assert (
        "https://dl/w.whl#sha256=aa"
        in (tmp_path / "simple/rn-forge-web/index.html").read_text()
    )
    assert (
        capsys.readouterr().out
        == f"wrote 1 projects and 1 files to {tmp_path / 'simple'}\n"
    )


def test_cli_index_refuses_a_page_outside_the_out_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.releases, "release_files", lambda repo: [])
    monkeypatch.setattr(
        cli.index, "render_index", lambda files: {"../escape.html": "x"}
    )
    out = tmp_path / "simple"
    assert cli.main(["index", "--repo", "o/r", "--out", str(out)]) == 1
    assert "escapes" in capsys.readouterr().err
    assert not (tmp_path / "escape.html").exists()


def test_index_and_releases_import_no_planner_adapter() -> None:
    code = (
        "import sys\n"
        "import rn_forge.devops.index, rn_forge.devops.releases\n"
        "print([m for m in ('rn_forge.devops.uv', 'rn_forge.devops.github')"
        " if m in sys.modules])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "[]"
