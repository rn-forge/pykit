"""The GitHub Actions adapter: `$GITHUB_OUTPUT` lines and the event context."""

from __future__ import annotations

import json
import os


def output_lines(outputs: dict[str, object]) -> list[str]:
    """Return `key=value` lines for `$GITHUB_OUTPUT`, with non-strings as JSON."""
    return [
        f"{key}={value if isinstance(value, str) else json.dumps(value)}"
        for key, value in outputs.items()
    ]


def sonar_branch(event: str, ref_type: str, ref_name: str) -> str:
    """Return the Sonar branch name to analyze, or "" to leave a pull request to the scanner.

    Raises:
        ValueError: For a tag ref, or any event other than push,
            workflow_dispatch and pull_request.
    """
    if event == "pull_request":
        return ""
    if event not in ("push", "workflow_dispatch"):
        raise ValueError(f"unsupported event for Sonar analysis: {event}")
    if ref_type != "branch":
        raise ValueError(
            f"unsupported ref for Sonar analysis: {ref_type} {ref_name}; run it on a branch"
        )
    return ref_name


def sonar_target() -> str:
    """Return the `branch-arg=` output line for the run in `EVENT_NAME`, `REF_TYPE` and `REF_NAME`.

    Raises:
        ValueError: As `sonar_branch`.
    """
    branch = sonar_branch(
        os.environ["EVENT_NAME"], os.environ["REF_TYPE"], os.environ["REF_NAME"]
    )
    return f"branch-arg=-Dsonar.branch.name={branch}" if branch else "branch-arg="
