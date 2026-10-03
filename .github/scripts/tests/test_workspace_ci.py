"""Tests for the Sonar target selection in `workspace_ci.py`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "workspace_ci", Path(__file__).resolve().parents[1] / "workspace_ci.py"
)
assert _SPEC is not None and _SPEC.loader is not None
workspace_ci: ModuleType = importlib.util.module_from_spec(_SPEC)
# dataclasses looks the module up in sys.modules while it executes.
sys.modules[_SPEC.name] = workspace_ci
_SPEC.loader.exec_module(workspace_ci)


@pytest.mark.parametrize(
    ("event", "ref_name", "expected"),
    [
        ("push", "main", "main"),
        ("workflow_dispatch", "feature/release-2", "feature/release-2"),
        ("workflow_dispatch", "fix/a_b.c-1/x+y", "fix/a_b.c-1/x+y"),
        ("workflow_dispatch", "main", "main"),
    ],
)
def test_branch_targets_exact_ref_name(
    event: str, ref_name: str, expected: str
) -> None:
    assert workspace_ci.sonar_branch(event, "branch", ref_name) == expected


@pytest.mark.parametrize("ref_name", ["12/merge", "feature/x"])
def test_pull_request_passes_no_branch(ref_name: str) -> None:
    # Fork PRs are skipped by the job's `if:`; the event alone decides here.
    assert workspace_ci.sonar_branch("pull_request", "branch", ref_name) == ""


@pytest.mark.parametrize("event", ["workflow_dispatch", "push"])
def test_tag_ref_is_unsupported(event: str) -> None:
    with pytest.raises(ValueError, match="unsupported ref"):
        workspace_ci.sonar_branch(event, "tag", "v1.0")


def test_unsupported_event() -> None:
    with pytest.raises(ValueError, match="unsupported event"):
        workspace_ci.sonar_branch("schedule", "branch", "main")


def _env(monkeypatch: pytest.MonkeyPatch, event: str, ref_type: str, name: str) -> None:
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("REF_TYPE", ref_type)
    monkeypatch.setenv("REF_NAME", name)


def test_cli_prints_branch_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "workflow_dispatch", "branch", "feature/release-2")
    monkeypatch.setattr("sys.argv", ["workspace_ci.py", "sonar-target"])
    assert workspace_ci.main() == 0
    assert capsys.readouterr().out == (
        "branch-arg=-Dsonar.branch.name=feature/release-2\n"
    )


def test_cli_prints_empty_argument_for_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "pull_request", "branch", "12/merge")
    monkeypatch.setattr("sys.argv", ["workspace_ci.py", "sonar-target"])
    assert workspace_ci.main() == 0
    assert capsys.readouterr().out == "branch-arg=\n"


def test_cli_exits_with_message_for_tag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, "workflow_dispatch", "tag", "v1.0")
    monkeypatch.setattr("sys.argv", ["workspace_ci.py", "sonar-target"])
    with pytest.raises(SystemExit) as exit_info:
        workspace_ci.main()
    assert "unsupported ref" in str(exit_info.value.code)
    assert capsys.readouterr().out == ""
