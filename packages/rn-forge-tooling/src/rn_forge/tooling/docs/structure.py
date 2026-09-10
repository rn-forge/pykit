"""Validate a docs tree against the area model the repository declares.

Checks only what is mechanically decidable: area scaffolding, file naming, ADR
numbering and status, link and anchor resolution, that no `_*.md` file is
referenced from a page that ships, and that the root instruction file points at
the docs rules. It does not judge prose, page length, or whether content sits
in the right area — that is review, and review is a runbook, not a checker.
"""

from __future__ import annotations

import re
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.tooling.docs.areas import Area, load_areas
from rn_forge.tooling.docs.markdown import headings, is_external, links

__all__ = ["INSTRUCTION_FILES", "check_structure"]

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
ADR_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
EPIC_DIR_RE = re.compile(r"^E(\d+)-[a-z0-9-]+$")
FEATURE_FILE_RE = re.compile(r"^F(\d+)\.(\d+)-[a-z0-9-]+\.md$")
RELEASE_DIR_RE = re.compile(r"^release-(\d+)$")
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.MULTILINE)
ALLOWED_ADR_STATUS = re.compile(
    r"^(proposed|accepted|deprecated|superseded by adr-\d{4})"
)
"""Matched against a lowercased status line, so the ADR token is lowercase here.

The donor script compared a lowercased status against an uppercase ``ADR-``,
which rejected every superseded ADR; the check is only useful if the one
status that names another decision can actually pass it.
"""

INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")
"""Root instruction files, in the order they are looked for."""


def _error(code: str, path: Path, message: str) -> Finding:
    return Finding(
        code=f"docs.{code}", severity=Severity.ERROR, message=message, path=str(path)
    )


def _clean_status(value: str) -> str:
    """Strip a trailing Markdown hard-line-break backslash (``accepted \\``)."""
    return value.strip().rstrip("\\").strip()


def _content_pages(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*.md")
        if path.name != "index.md" and not path.name.startswith("_")
    )


def _check_areas(areas: list[Area], docs_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for area in areas:
        if area.generated:
            continue
        target = docs_root / area.key
        if not target.is_dir():
            if not area.optional:
                findings.append(
                    _error("missing-area", target, f"{area.key}/ does not exist")
                )
            continue
        for required, code in (
            ("_structure.md", "missing-structure-md"),
            ("index.md", "missing-index"),
        ):
            if not (target / required).exists():
                findings.append(_error(code, target, f"{area.key}/ has no {required}"))
    return findings


def _check_naming(areas: list[Area], docs_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    for area in areas:
        area_dir = docs_root / area.key
        if area.generated or area.key == "adr" or not area_dir.is_dir():
            continue
        findings.extend(
            _error("kebab-case", path, "not kebab-case")
            for path in _content_pages(area_dir)
            if not KEBAB_RE.match(path.name)
        )

    findings.extend(_check_adr_naming(docs_root / "adr"))
    findings.extend(_check_release_naming(docs_root / "releases"))
    findings.extend(_check_epic_naming(docs_root / "specs" / "epics"))
    return findings


def _check_adr_naming(adr_dir: Path) -> list[Finding]:
    if not adr_dir.is_dir():
        return []
    findings: list[Finding] = []
    numbers: list[int] = []
    for path in _content_pages(adr_dir):
        match = ADR_RE.match(path.name)
        if not match:
            findings.append(
                _error("adr-naming", path, "does not match <nnnn>-<slug>.md")
            )
            continue
        numbers.append(int(match.group(1)))
    if len(numbers) != len(set(numbers)):
        findings.append(
            _error("adr-duplicate-number", adr_dir, "duplicate ADR numbers")
        )
    for expected, actual in enumerate(sorted(set(numbers)), start=1):
        if expected != actual:
            findings.append(
                _error(
                    "adr-number-gap",
                    adr_dir,
                    f"expected {expected:04d}, found {actual:04d}",
                )
            )
            break
    return findings


def _check_release_naming(releases_dir: Path) -> list[Finding]:
    if not releases_dir.is_dir():
        return []
    findings: list[Finding] = []
    for path in sorted(p for p in releases_dir.iterdir() if p.is_dir()):
        if not RELEASE_DIR_RE.match(path.name):
            findings.append(
                _error("release-naming", path, "does not match release-<n>/")
            )
        elif not (path / "index.md").exists():
            findings.append(
                _error("release-missing-index", path, "release-<n>/ has no index.md")
            )
    return findings


def _check_epic_naming(epics_dir: Path) -> list[Finding]:
    if not epics_dir.is_dir():
        return []
    findings: list[Finding] = []
    for path in sorted(p for p in epics_dir.iterdir() if p.is_dir()):
        if not EPIC_DIR_RE.match(path.name):
            findings.append(_error("epic-naming", path, "does not match E<n>-<slug>/"))
        findings.extend(
            _error("feature-naming", feature_path, "does not match F<n>.<m>-<slug>.md")
            for feature_path in sorted(path.glob("F*.md"))
            if not FEATURE_FILE_RE.match(feature_path.name)
        )
    return findings


def _check_adr_status(docs_root: Path) -> list[Finding]:
    adr_dir = docs_root / "adr"
    if not adr_dir.is_dir():
        return []
    findings: list[Finding] = []
    for path in _content_pages(adr_dir):
        match = STATUS_RE.search(path.read_text(encoding="utf-8"))
        if not match or not ALLOWED_ADR_STATUS.match(
            _clean_status(match.group(1)).lower()
        ):
            findings.append(
                _error("adr-status", path, "missing or invalid **Status:** line")
            )
    return findings


def _check_links(docs_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(docs_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for link in links(text):
            if is_external(link):
                continue
            target, _, anchor = link.partition("#")
            if not target:
                if anchor and anchor not in headings(text):
                    findings.append(
                        _error(
                            "broken-anchor", path, f"#{anchor} not found in same page"
                        )
                    )
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                findings.append(_error("broken-link", path, f"{link} does not resolve"))
                continue
            if (
                anchor
                and resolved.suffix == ".md"
                and anchor not in headings(resolved.read_text(encoding="utf-8"))
            ):
                findings.append(
                    _error("broken-anchor", path, f"{link} anchor not found")
                )
    return findings


def _check_no_underscore_refs(docs_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(docs_root.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        findings.extend(
            _error("underscore-referenced", path, f"links to {link}")
            for link in links(path.read_text(encoding="utf-8"))
            if (name := Path(link.partition("#")[0]).name).startswith("_")
            and not name.startswith("__")
        )
    return findings


def _resolved_links(path: Path) -> set[Path]:
    return {
        (path.parent / link.partition("#")[0]).resolve()
        for link in links(path.read_text(encoding="utf-8"))
        if not is_external(link)
    }


def _check_instruction_pointer(repo_root: Path, docs_root: Path) -> list[Finding]:
    """Some instruction file must link both `docs/_structure.md` and `docs/index.md`.

    That is the only route into the rules for a session that has read neither
    the generator nor this checker. It is deliberately not "every instruction
    file links both": instructions are single-sourced, so `AGENTS.md` is a
    pointer at `CLAUDE.md` rather than a second copy that can drift. What
    matters is that following the links from whichever file an agent opened
    first arrives at the rules.
    """
    present = [
        repo_root / name for name in INSTRUCTION_FILES if (repo_root / name).exists()
    ]
    if not present:
        return [
            _error(
                "missing-instruction-file",
                repo_root,
                f"no instruction file: expected one of {', '.join(INSTRUCTION_FILES)}",
            )
        ]

    wanted = {(docs_root / name).resolve() for name in ("_structure.md", "index.md")}
    carriers = [path for path in present if wanted <= _resolved_links(path)]
    if not carriers:
        return [
            _error(
                "missing-docs-pointer",
                path,
                f"no instruction file links both {docs_root.name}/_structure.md "
                f"and {docs_root.name}/index.md",
            )
            for path in present
        ]

    carrier_paths = {path.resolve() for path in carriers}
    return [
        _error(
            "missing-docs-pointer",
            path,
            "neither links the docs rules nor points at "
            f"{', '.join(sorted(p.name for p in carrier_paths))}",
        )
        for path in present
        if path.resolve() not in carrier_paths
        and not (_resolved_links(path) & carrier_paths)
    ]


def check_structure(repo_root: str | Path, docs_root: str | Path) -> list[Finding]:
    """Run every structure check, returning the findings in reporting order.

    Args:
        repo_root: The repository root, where the instruction files live.
        docs_root: The docs tree, normally ``<repo_root>/docs``.
    """
    repo_root = Path(repo_root)
    docs_root = Path(docs_root)
    try:
        areas = load_areas(docs_root)
    except AppException as exc:
        return [_error("areas-manifest", docs_root, str(exc))]

    return [
        *_check_areas(areas, docs_root),
        *_check_naming(areas, docs_root),
        *_check_adr_status(docs_root),
        *_check_links(docs_root),
        *_check_no_underscore_refs(docs_root),
        *_check_instruction_pointer(repo_root, docs_root),
    ]
