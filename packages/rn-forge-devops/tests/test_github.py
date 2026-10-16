"""Tests for the GitHub Actions adapter's Sonar target selection."""

from __future__ import annotations

import pytest

from rn_forge.devops import github


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
    assert github.sonar_branch(event, "branch", ref_name) == expected


@pytest.mark.parametrize("ref_name", ["12/merge", "feature/x"])
def test_pull_request_passes_no_branch(ref_name: str) -> None:
    # Fork PRs are skipped by the job's `if:`; the event alone decides here.
    assert github.sonar_branch("pull_request", "branch", ref_name) == ""


@pytest.mark.parametrize("event", ["workflow_dispatch", "push"])
def test_tag_ref_is_unsupported(event: str) -> None:
    with pytest.raises(ValueError, match="unsupported ref"):
        github.sonar_branch(event, "tag", "v1.0")


def test_unsupported_event() -> None:
    with pytest.raises(ValueError, match="unsupported event"):
        github.sonar_branch("schedule", "branch", "main")
