"""Generate `mkdocs.yml` navigation from `docs/_areas.yml` and the docs tree.

Pages are ordered with `index.md` first, followed by its linked pages in link
order, then all remaining pages alphabetically.
"""

from __future__ import annotations

from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.fs.documents import YamlUtils
from rn_forge.tooling.docs.areas import Area, load_areas
from rn_forge.tooling.docs.markdown import is_external, links

__all__ = [
    "ACRONYMS",
    "NAV_BLOCK",
    "NavEntry",
    "build_nav",
    "title_from_filename",
    "update_nav",
]

NAV_BLOCK = ManagedBlock("generated nav", indent="  ")
"""The fenced block inside `mkdocs.yml`'s ``nav:`` that this module owns."""

ACRONYMS = {"adr": "ADR", "api": "API", "cli": "CLI", "ci": "CI", "id": "ID"}
"""Filename words that are capitalised rather than title-cased."""


def title_from_filename(name: str) -> str:
    """Turn ``task-cli-api.md`` into ``Task CLI API``."""
    stem = name.removesuffix(".md")
    return " ".join(
        ACRONYMS.get(word.lower(), word.capitalize()) for word in stem.split("-")
    )


def _linked_order(index_path: Path) -> list[str]:
    if not index_path.exists():
        return []
    return [
        link.partition("#")[0]
        for link in links(index_path.read_text(encoding="utf-8"))
        if not is_external(link) and link.partition("#")[0].endswith(".md")
    ]


def _children_entries(docs_root: Path, area_key: str) -> list[tuple[str, str]]:
    area_dir = docs_root / area_key
    index_path = area_dir / "index.md"

    ordered: list[str] = []
    if index_path.exists():
        ordered.append(f"{area_key}/index.md")
    for link in _linked_order(index_path):
        rel = link if link.startswith(f"{area_key}/") else f"{area_key}/{link}"
        if (docs_root / rel).exists() and rel not in ordered:
            ordered.append(rel)
    for page in sorted(area_dir.glob("*.md")):
        rel = f"{area_key}/{page.name}"
        if page.name == "index.md" or page.name.startswith("_") or rel in ordered:
            continue
        ordered.append(rel)

    return [
        (
            "Overview"
            if Path(rel).name == "index.md"
            else title_from_filename(Path(rel).name),
            rel,
        )
        for rel in ordered
    ]


NavEntry = dict[str, "str | list[NavEntry]"]
"""One mkdocs nav entry: a title mapped to a page path or to nested entries."""

BLOCK_INDENT = "  "
"""What every serialized nav line is indented by, to sit under ``nav:``."""


def _area_entry(docs_root: Path, area: Area) -> NavEntry | None:
    """The nav entry for *area*, or ``None`` when it contributes nothing."""
    area_dir = docs_root / area.key
    if (area.optional or area.generated) and not area_dir.is_dir():
        return None
    if area.nav == "index-only":
        return {area.title: f"{area.key}/index.md"}
    entries = _children_entries(docs_root, area.key)
    if not entries:
        return None
    return {area.title: [{title: rel} for title, rel in entries]}


def build_nav(docs_root: str | Path) -> str:
    """Render the nav block's body for the docs tree at *docs_root*."""
    docs_root = Path(docs_root)
    nav: list[NavEntry] = [{"Home": "index.md"}]
    nav.extend(
        entry
        for area in load_areas(docs_root)
        if (entry := _area_entry(docs_root, area)) is not None
    )
    serialized = YamlUtils.serialize(nav)
    return "".join(
        f"{BLOCK_INDENT}{line}\n" if line else "\n" for line in serialized.splitlines()
    )


def update_nav(mkdocs_path: str | Path, docs_root: str | Path) -> tuple[str, bool]:
    """Return `mkdocs.yml`'s new text and whether it differs from what is on disk.

    Writes nothing — the caller decides whether this is a check or a rewrite.

    Raises:
        AppException: The nav block's markers are missing or malformed.
    """
    mkdocs_path = Path(mkdocs_path)
    current = mkdocs_path.read_text(encoding="utf-8")
    if NAV_BLOCK.extract(current) is None:
        raise AppException(
            "{} has no {!r} / {!r} markers",
            mkdocs_path,
            NAV_BLOCK.begin.strip(),
            NAV_BLOCK.end.strip(),
        )
    updated = NAV_BLOCK.render(current, build_nav(docs_root))
    return updated, updated != current
