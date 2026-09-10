"""Validate a docs tree against the area model and the policy the caller supplies.

Checks only what is mechanically decidable: area scaffolding, file naming,
numbered-series numbering and status, link and anchor resolution, that no
`_*.md` file is referenced from a page that ships, and that the root
instruction file points at the docs rules. It does not judge prose, page
length, or whether content sits in the right area — that is review, and review
is a runbook, not a checker.

What counts as a numbered series, what its statuses may say, how release or
epic directories are named and what the instruction files are called are **not
here**: they are one organisation's decisions, and they arrive as a
:class:`~rn_forge.tooling.docs.policy.DocsPolicy`.
"""

from __future__ import annotations

from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.tooling.docs.areas import Area, load_areas
from rn_forge.tooling.docs.markdown import headings, is_external, links
from rn_forge.tooling.docs.policy import (
    STATUS_LINE,
    DocsPolicy,
    NestedArea,
    NumberedArea,
    SequenceArea,
)

__all__ = ["check_structure"]


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


def _check_naming(
    areas: list[Area], docs_root: Path, policy: DocsPolicy
) -> list[Finding]:
    findings: list[Finding] = []
    policy_areas = {
        *([policy.numbered.path] if policy.numbered else []),
        *(area.path for area in policy.sequences),
        *(area.path for area in policy.nested),
    }

    for area in areas:
        area_dir = docs_root / area.key
        if area.generated or area.key in policy_areas or not area_dir.is_dir():
            continue
        findings.extend(
            _error("kebab-case", path, "not kebab-case")
            for path in _content_pages(area_dir)
            if not policy.page_name.match(path.name)
        )

    if policy.numbered:
        findings.extend(_check_numbered_naming(docs_root, policy.numbered))
    for sequence in policy.sequences:
        findings.extend(_check_sequence_naming(docs_root / sequence.path, sequence))
    for nested in policy.nested:
        findings.extend(_check_nested_naming(docs_root / nested.path, nested))
    return findings


def _check_numbered_naming(docs_root: Path, series: NumberedArea) -> list[Finding]:
    """Every page named to the series' shape, numbered uniquely and without gaps."""
    directory = docs_root / series.path
    if not directory.is_dir():
        return []
    findings: list[Finding] = []
    numbers: list[int] = []
    for path in _content_pages(directory):
        match = series.filename.match(path.name)
        if not match:
            findings.append(_error("naming", path, f"does not match {series.shape}"))
            continue
        numbers.append(int(match.group(1)))
    if len(numbers) != len(set(numbers)):
        findings.append(
            _error(
                "duplicate-number",
                directory,
                f"duplicate {series.label} numbers",
            )
        )
    width = len(str(max(numbers))) if numbers else 1
    for expected, actual in enumerate(sorted(set(numbers)), start=1):
        if expected != actual:
            findings.append(
                _error(
                    "number-gap",
                    directory,
                    f"expected {expected:0{width}d}, found {actual:0{width}d}",
                )
            )
            break
    return findings


def _check_sequence_naming(directory: Path, sequence: SequenceArea) -> list[Finding]:
    """Every child directory named to the shape, each with an ``index.md``."""
    if not directory.is_dir():
        return []
    findings: list[Finding] = []
    for path in sorted(p for p in directory.iterdir() if p.is_dir()):
        if not sequence.dirname.match(path.name):
            findings.append(_error("naming", path, f"does not match {sequence.shape}"))
        elif not (path / "index.md").exists():
            findings.append(
                _error("missing-index", path, f"{sequence.shape} has no index.md")
            )
    return findings


def _check_nested_naming(directory: Path, nested: NestedArea) -> list[Finding]:
    """Every container directory, and the pages inside it, named to the shape."""
    if not directory.is_dir():
        return []
    findings: list[Finding] = []
    for path in sorted(p for p in directory.iterdir() if p.is_dir()):
        if not nested.dirname.match(path.name):
            findings.append(
                _error("naming", path, f"does not match {nested.dir_shape}")
            )
        findings.extend(
            _error("naming", page, f"does not match {nested.page_shape}")
            for page in sorted(path.glob(nested.page_glob))
            if not nested.page_name.match(page.name)
        )
    return findings


def _check_status(docs_root: Path, series: NumberedArea) -> list[Finding]:
    """Every page in the numbered series carries a status the policy allows."""
    directory = docs_root / series.path
    if not directory.is_dir():
        return []
    findings: list[Finding] = []
    for path in _content_pages(directory):
        match = STATUS_LINE.search(path.read_text(encoding="utf-8"))
        if not match or not series.statuses.match(
            _clean_status(match.group(1)).lower()
        ):
            findings.append(
                _error("status", path, "missing or invalid **Status:** line")
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


def _check_instruction_pointer(
    repo_root: Path, docs_root: Path, instruction_files: tuple[str, ...]
) -> list[Finding]:
    """Some instruction file must link both `docs/_structure.md` and `docs/index.md`.

    That is the only route into the rules for a session that has read neither
    the generator nor this checker. It is deliberately not "every instruction
    file links both": instructions are single-sourced, so the second file a
    policy names is normally a pointer at the first rather than a copy that can
    drift. What matters is that following the links from whichever file an
    agent opened first arrives at the rules.

    Which files those are is the caller's policy, not this module's.
    """
    present = [
        repo_root / name for name in instruction_files if (repo_root / name).exists()
    ]
    if not present:
        return [
            _error(
                "missing-instruction-file",
                repo_root,
                f"no instruction file: expected one of {', '.join(instruction_files)}",
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


def check_structure(
    repo_root: str | Path, docs_root: str | Path, policy: DocsPolicy
) -> list[Finding]:
    """Run every structure check, returning the findings in reporting order.

    Args:
        repo_root: The repository root, where the instruction files live.
        docs_root: The docs tree, normally ``<repo_root>/docs``.
        policy: The repository's own conventions. Required, and deliberately
            without a default — see :mod:`rn_forge.tooling.docs.policy`.
    """
    repo_root = Path(repo_root)
    docs_root = Path(docs_root)
    try:
        areas = load_areas(docs_root)
    except AppException as exc:
        return [_error("areas-manifest", docs_root, str(exc))]

    return [
        *_check_areas(areas, docs_root),
        *_check_naming(areas, docs_root, policy),
        *(_check_status(docs_root, policy.numbered) if policy.numbered else []),
        *_check_links(docs_root),
        *_check_no_underscore_refs(docs_root),
        *_check_instruction_pointer(repo_root, docs_root, policy.instruction_files),
    ]
