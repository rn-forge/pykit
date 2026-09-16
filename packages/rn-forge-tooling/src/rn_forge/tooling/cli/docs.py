"""Command-line interface for documentation structure, link, and nav checks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.cli import CliApp
from rn_forge.commons.runtime.console import OutputMode, console
from rn_forge.tooling.docs.nav import update_nav
from rn_forge.tooling.docs.policy import DocsPolicy
from rn_forge.tooling.docs.site import check_site
from rn_forge.tooling.docs.structure import check_structure

__all__ = ["app"]

app = CliApp("rn-forge-docs", "Documentation structure, link and nav checks.")

RootOption = Annotated[
    Path,
    typer.Option("--root", help="Repository root.", show_default="."),
]
DocsRootOption = Annotated[
    Path,
    typer.Option("--docs-root", help="Docs directory, relative to the root."),
]
PolicyOption = Annotated[
    str,
    typer.Option(
        "--policy",
        help="Import path of this repository's DocsPolicy, as module:attribute.",
    ),
]


def _load_policy(reference: str) -> DocsPolicy:
    """Import the :class:`DocsPolicy` *reference* names.

    Raises:
        typer.BadParameter: The reference does not import, or does not name a
            policy.
    """
    try:
        policy = AppUtils.import_string(reference)
    except (AppException, ImportError, AttributeError, ValueError) as error:
        raise typer.BadParameter(f"cannot import {reference!r}: {error}") from error
    if not isinstance(policy, DocsPolicy):
        raise typer.BadParameter(f"{reference!r} is not a DocsPolicy")
    return policy


def _report(findings: list[Finding], *, passed: str) -> None:
    """Print *findings* and exit non-zero if any of them is an error."""
    if console.mode is OutputMode.JSON:
        console.emit({"findings": [finding.as_dict() for finding in findings]})
    else:
        for finding in findings:
            console.error(str(finding))
    if any(finding.is_error for finding in findings):
        raise typer.Exit(1)
    if console.mode is not OutputMode.JSON:
        console.success(passed)


@app.command()
def structure(
    policy: PolicyOption,
    root: RootOption = Path(),
    docs_root: DocsRootOption = Path("docs"),
) -> None:
    """Check the docs tree against the area model and policy the repository declares."""
    _report(
        check_structure(root, root / docs_root, _load_policy(policy)),
        passed="docs structure check passed",
    )


@app.command()
def check(
    root: RootOption = Path(),
    docs_root: DocsRootOption = Path("docs"),
) -> None:
    """Check links, anchors, nav targets and orphan pages."""
    _report(check_site(root, docs_dir=str(docs_root)), passed="docs check passed")


@app.command()
def nav(
    root: RootOption = Path(),
    docs_root: DocsRootOption = Path("docs"),
    check_only: Annotated[
        bool,
        typer.Option(
            "--check", help="Fail if the nav block is stale instead of rewriting it."
        ),
    ] = False,
) -> None:
    """Regenerate `mkdocs.yml`'s nav block from the docs tree."""
    mkdocs_path = root / "mkdocs.yml"
    updated, changed = update_nav(mkdocs_path, root / docs_root)
    written = changed and not check_only
    if written:
        mkdocs_path.write_text(updated, encoding="utf-8")

    if console.mode is OutputMode.JSON:
        # A --json run must emit a result whichever branch it took: a command
        # that changes a file and prints nothing gives a caller no way to tell
        # success from a silent no-op.
        console.emit(
            {
                "path": str(mkdocs_path),
                "stale": changed,
                "written": written,
                "checked": check_only,
            }
        )
    elif check_only and changed:
        console.error("mkdocs.yml nav is stale; run `task docs:nav`")
    elif check_only:
        console.success("nav is up to date")
    elif written:
        console.success("updated {}", mkdocs_path)
    else:
        console.info("no change")

    if check_only and changed:
        raise typer.Exit(1)
