"""``rn-forge-docs`` — the docs checkers as a command.

Three commands, matching the three public docs tasks a repository's Taskfile
wires up::

    rn-forge-docs structure          # the tree matches docs/_areas.yml
    rn-forge-docs check              # links, anchors, nav targets, orphans
    rn-forge-docs nav [--check]      # regenerate mkdocs.yml's nav block

Each exits non-zero when it produces an error-severity finding, and each
accepts ``--json`` for machine-readable output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from rn_forge.commons.findings import Finding
from rn_forge.tooling.cli import build_app
from rn_forge.tooling.console import OutputMode, console
from rn_forge.tooling.docs.nav import update_nav
from rn_forge.tooling.docs.site import check_site
from rn_forge.tooling.docs.structure import check_structure

__all__ = ["app"]

app = build_app("rn-forge-docs", "Documentation structure, link and nav checks.")

RootOption = Annotated[
    Path,
    typer.Option("--root", help="Repository root.", show_default="."),
]
DocsRootOption = Annotated[
    Path,
    typer.Option("--docs-root", help="Docs directory, relative to the root."),
]


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
    root: RootOption = Path(),
    docs_root: DocsRootOption = Path("docs"),
) -> None:
    """Check the docs tree against the area model the repository declares."""
    _report(
        check_structure(root, root / docs_root), passed="docs structure check passed"
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
    if check_only:
        if changed:
            console.error("mkdocs.yml nav is stale; run `task docs:nav`")
            raise typer.Exit(1)
        console.success("nav is up to date")
        return
    if changed:
        mkdocs_path.write_text(updated, encoding="utf-8")
        console.success("updated {}", mkdocs_path)
    else:
        console.info("no change")
