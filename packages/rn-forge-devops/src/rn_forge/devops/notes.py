"""The umbrella release for a shipped release page."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

_PAGE_DIR = re.compile(r"release-(\d+)")
_STATUS = re.compile(r"^\|[ \t]*\*\*Status\*\*[ \t]*\|([^\n]*)\|[ \t]*$", re.MULTILINE)
_TITLE = re.compile(r"^#[ \t]+(\S[^\n]*)$", re.MULTILINE)
_SHIPPED_HEADING = re.compile(r"## Shipped[ \t]*")


def _shipped_section(text: str) -> str | None:
    """Return the lines under `## Shipped` up to the next `## ` heading."""
    body: list[str] = []
    inside = False
    for line in text.splitlines(keepends=True):
        if inside:
            if line.startswith("## "):
                break
            body.append(line)
        elif _SHIPPED_HEADING.fullmatch(line.rstrip("\r\n")):
            inside = True
    return "".join(body) if inside else None


@dataclass(frozen=True, slots=True)
class Umbrella:
    """The GitHub release that announces a shipped release page."""

    tag: str
    """The release tag, for example `release-6`."""
    title: str
    """The page's H1 text."""
    body: str
    """The release notes: the page's `## Shipped` section and a link to the page."""


def pending_umbrella(
    releases_dir: Path, existing_tags: Collection[str], site_url: str
) -> Umbrella | None:
    """Return the umbrella release for the newest shipped release page.

    Only the newest page whose `| **Status** |` row starts with `shipped` is
    considered, so older pages are never backfilled.

    Args:
        releases_dir: A directory of `release-<n>/index.md` pages.
        existing_tags: The repository's existing tag names.
        site_url: The documentation site's URL, ending in `/`.

    Returns:
        The umbrella release, or `None` when no page is shipped or its tag
        already exists.
    """
    shipped: list[tuple[int, Path]] = []
    for page in releases_dir.glob("release-*/index.md"):
        number = _PAGE_DIR.fullmatch(page.parent.name)
        if number is None:
            continue
        status = _STATUS.search(page.read_text(encoding="utf-8"))
        if status and status.group(1).strip().startswith("shipped"):
            shipped.append((int(number.group(1)), page))
    if not shipped:
        return None
    number, page = max(shipped)
    tag = f"release-{number}"
    if tag in existing_tags:
        return None
    text = page.read_text(encoding="utf-8")
    title = _TITLE.search(text)
    section = _shipped_section(text)
    if title is None or section is None:
        raise ValueError(f"{page} needs an H1 title and a `## Shipped` section")
    link = f"Release page: {site_url}releases/{tag}/"
    return Umbrella(tag, title.group(1).strip(), f"{section.strip()}\n\n{link}\n")
