"""Tests for the `rn-forge-devops` console script."""

from __future__ import annotations

from pathlib import Path

import pytest

from rn_forge.devops import cli


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
