"""Run the workspace's coverage tests and a SonarCloud branch analysis from a local checkout.

The scope comes from `workspace_ci.py plan`. A full run uploads the working tree to
SonarCloud and needs `SONAR_TOKEN` and an installed `sonar-scanner`. The development
guide describes the prerequisites.

Usage:
    sonar_local.py --dry-run          print the target and the commands; run nothing
    sonar_local.py [--branch NAME]    run the tests, then the scan, and exit with the gate status
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANNER = Path(__file__).resolve().parent / "workspace_ci.py"
SONAR_URL = "https://sonarcloud.io"
SCANNER_DIR = ".sonar-cleanup/scanner"


def read_plan() -> dict[str, str]:
    """Return the planner's `key=value` lines, split on the first `=`."""
    result = subprocess.run(
        [sys.executable, str(PLANNER), "plan", ""],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def resolve_branch(requested: str | None) -> str:
    """Return the branch to analyze.

    Raises:
        ValueError: On `main`, on a detached HEAD without `requested`, or when
            `requested` differs from the checked-out branch.
    """
    current = git("branch", "--show-current")
    if not current and not requested:
        raise ValueError("detached HEAD: pass --branch with the branch name")
    if current and requested and requested != current:
        raise ValueError(f"--branch {requested!r} differs from checked-out {current!r}")
    branch = requested or current
    if branch == "main":
        raise ValueError("refusing to upload a local scan as main")
    return branch


def local_env() -> dict[str, str]:
    """Return the environment without CI metadata that triggers scanner autodetection."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "CI" and not key.startswith("GITHUB_")
    }


def commands(plan: dict[str, str], branch: str) -> tuple[list[str], list[str]]:
    """Return the coverage test command and the scanner command."""
    tests = [
        "uv",
        "run",
        "pytest",
        *shlex.split(plan["cov-args"]),
        "--cov-report=xml:coverage.xml",
        *shlex.split(plan["test-paths"]),
    ]
    scanner = [
        "sonar-scanner",
        f"-Dsonar.host.url={SONAR_URL}",
        f"-Dsonar.sources={plan['sonar-sources']}",
        f"-Dsonar.tests={plan['sonar-tests']}",
        f"-Dsonar.branch.name={branch}",
        "-Dsonar.qualitygate.wait=true",
        f"-Dsonar.working.directory={SCANNER_DIR}",
    ]
    return tests, scanner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--branch")
    args = parser.parse_args(argv)

    try:
        branch = resolve_branch(args.branch)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    tests, scanner = commands(read_plan(), branch)

    print(f"target: {branch}")
    if git("status", "--porcelain"):
        print(
            "note: the working tree has uncommitted changes; this scan is not CI "
            "evidence for any commit"
        )
    if args.dry_run:
        print(shlex.join(tests))
        print(shlex.join(scanner))
        return 0

    if not os.environ.get("SONAR_TOKEN"):
        print("error: SONAR_TOKEN is not set", file=sys.stderr)
        return 2
    if shutil.which("sonar-scanner") is None:
        print("error: sonar-scanner is not installed", file=sys.stderr)
        return 2

    status = subprocess.run(tests, cwd=ROOT).returncode
    if status:
        return status
    return subprocess.run(scanner, cwd=ROOT, env=local_env()).returncode


if __name__ == "__main__":
    sys.exit(main())
