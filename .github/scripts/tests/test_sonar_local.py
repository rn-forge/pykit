"""Tests for `sonar_local.py` with git, uv and the scanner mocked."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "sonar_local", Path(__file__).resolve().parents[1] / "sonar_local.py"
)
assert _SPEC is not None and _SPEC.loader is not None
sonar_local: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sonar_local
_SPEC.loader.exec_module(sonar_local)

TOKEN = "s3cret-token-value"
PLAN = "\n".join(
    [
        "release-order=[]",
        "cov-args=--cov=pkg.a --cov='pkg b;x'",
        "test-paths=packages/a 'packages/b c;d'",
        "sonar-sources=packages/a/src,packages/b/src",
        "sonar-tests=packages/a/tests",
        "sonar=true",
    ]
)


class Fake:
    """Stands in for `subprocess.run`, recording each call."""

    def __init__(self, branch: str = "feature/x", dirty: str = "") -> None:
        self.branch = branch
        self.dirty = dirty
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.test_status = 0
        self.scan_status = 0

    def __call__(
        self, cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        assert isinstance(cmd, list)
        assert not kwargs.get("shell")
        self.calls.append((cmd, kwargs))
        out, status = "", 0
        if cmd[0] == "git" and cmd[1] == "branch":
            out = self.branch + "\n"
        elif cmd[0] == "git" and cmd[1] == "status":
            out = self.dirty
        elif cmd[0] == sys.executable:
            out = PLAN
        elif cmd[0] == "uv":
            status = self.test_status
        elif cmd[0] == "sonar-scanner":
            status = self.scan_status
        return subprocess.CompletedProcess(cmd, status, out, "")

    def ran(self, name: str) -> list[tuple[list[str], dict[str, Any]]]:
        return [c for c in self.calls if c[0][0] == name]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Fake:
    fake = Fake()
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(sonar_local.shutil, "which", lambda _name: "/bin/sonar-scanner")
    monkeypatch.setenv("SONAR_TOKEN", TOKEN)
    return fake


def test_scope_comes_from_planner_output(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sonar_local.main([]) == 0
    tests = fake.ran("uv")[0][0]
    scanner = fake.ran("sonar-scanner")[0][0]
    assert tests == [
        "uv", "run", "pytest", "--cov=pkg.a", "--cov=pkg b;x",
        "--cov-report=xml:coverage.xml", "packages/a", "packages/b c;d",
    ]  # fmt: skip
    assert scanner == [
        "sonar-scanner",
        "-Dsonar.host.url=https://sonarcloud.io",
        "-Dsonar.sources=packages/a/src,packages/b/src",
        "-Dsonar.tests=packages/a/tests",
        "-Dsonar.branch.name=feature/x",
        "-Dsonar.qualitygate.wait=true",
        "-Dsonar.working.directory=.sonar-cleanup/scanner",
    ]
    assert fake.calls[0][1]["cwd"] == sonar_local.ROOT
    assert "target: feature/x" in capsys.readouterr().out


def test_dry_run_prints_commands_without_token_or_execution(
    fake: Fake, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SONAR_TOKEN")
    monkeypatch.setattr(sonar_local.shutil, "which", lambda _name: None)
    assert sonar_local.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "'--cov=pkg b;x'" in out
    assert "sonar-scanner -Dsonar.host.url=https://sonarcloud.io" in out
    assert not fake.ran("uv") and not fake.ran("sonar-scanner")


def test_missing_token(
    fake: Fake, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SONAR_TOKEN")
    assert sonar_local.main([]) != 0
    assert "SONAR_TOKEN" in capsys.readouterr().err
    assert not fake.ran("uv")


def test_missing_scanner(
    fake: Fake, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sonar_local.shutil, "which", lambda _name: None)
    assert sonar_local.main([]) != 0
    assert "sonar-scanner is not installed" in capsys.readouterr().err
    assert not fake.ran("uv")


def test_token_is_never_in_argv_or_output(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sonar_local.main([]) == 0
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert all(TOKEN not in part for cmd, _ in fake.calls for part in cmd)
    assert fake.ran("sonar-scanner")[0][1]["env"]["SONAR_TOKEN"] == TOKEN


@pytest.mark.parametrize(
    ("branch", "argv"),
    [("main", []), ("main", ["--branch", "main"]), ("", ["--branch", "main"])],
)
def test_main_is_rejected(
    fake: Fake, branch: str, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    fake.branch = branch
    assert sonar_local.main(argv) != 0
    assert "main" in capsys.readouterr().err
    assert not fake.ran("uv") and not fake.ran("sonar-scanner")


def test_detached_head_requires_branch(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.branch = ""
    assert sonar_local.main([]) != 0
    assert "detached HEAD" in capsys.readouterr().err
    assert sonar_local.main(["--branch", "feature/y"]) == 0
    assert "-Dsonar.branch.name=feature/y" in fake.ran("sonar-scanner")[0][0]


def test_branch_must_match_checked_out_branch(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sonar_local.main(["--branch", "feature/other"]) != 0
    assert "differs" in capsys.readouterr().err
    assert not fake.ran("uv")


def test_dirty_tree_is_allowed_with_note(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.dirty = " M file.py\n"
    assert sonar_local.main(["--dry-run"]) == 0
    assert "not CI evidence" in capsys.readouterr().out


def test_inherited_ci_metadata_is_removed_from_scanner_env(
    fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    monkeypatch.setenv("KEEP_ME", "1")
    assert sonar_local.main([]) == 0
    env = fake.ran("sonar-scanner")[0][1]["env"]
    assert not {"CI", "GITHUB_ACTIONS", "GITHUB_REF"} & env.keys()
    assert env["KEEP_ME"] == "1"


def test_failing_tests_stop_before_scanning(fake: Fake) -> None:
    fake.test_status = 3
    assert sonar_local.main([]) == 3
    assert not fake.ran("sonar-scanner")


def test_scanner_failure_status_is_propagated(fake: Fake) -> None:
    fake.scan_status = 4
    assert sonar_local.main([]) == 4
