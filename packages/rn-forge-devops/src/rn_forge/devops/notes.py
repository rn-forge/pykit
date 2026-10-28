"""Release notes: a changelog section and the umbrella release for a shipped page."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

_PAGE_DIR = re.compile(r"release-(\d+)")
_STATUS = re.compile(r"^\|\s*\*\*Status\*\*\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SHIPPED = re.compile(r"^## Shipped[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class Umbrella:
    """The GitHub release that announces a shipped release page."""

    tag: str
    """The release tag, for example `release-6`."""
    title: str
    """The page's H1 text."""
    body: str
    """The release notes: the page's `## Shipped` section and a link to the page."""


def changelog_section(changelog: str, version: str) -> str:
    """Return the body under `## [<version>]` up to the next `## [` heading.

    The heading is `## [<version>]` followed by the end of the line or
    ` - <date>`; the version must match exactly.

    Args:
        changelog: The text of a Keep a Changelog file.
        version: The version whose section to return.

    Returns:
        The section body with surrounding whitespace removed.

    Raises:
        ValueError: The version has no heading, or its body is empty.
    """
    heading = re.compile(
        rf"^## \[{re.escape(version)}\](?: - .*)?[ \t]*$", re.MULTILINE
    )
    match = heading.search(changelog)
    if match is None:
        raise ValueError(f"no `## [{version}]` heading in the changelog")
    rest = changelog[match.end() :]
    following = re.search(r"^## \[", rest, re.MULTILINE)
    body = (rest[: following.start()] if following else rest).strip()
    if not body:
        raise ValueError(f"the `## [{version}]` section is empty")
    return body


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
        if status and status.group(1).startswith("shipped"):
            shipped.append((int(number.group(1)), page))
    if not shipped:
        return None
    number, page = max(shipped)
    tag = f"release-{number}"
    if tag in existing_tags:
        return None
    text = page.read_text(encoding="utf-8")
    title = _TITLE.search(text)
    section = _SHIPPED.search(text)
    if title is None or section is None:
        raise ValueError(f"{page} needs an H1 title and a `## Shipped` section")
    link = f"Release page: {site_url}releases/{tag}/"
    return Umbrella(tag, title.group(1), f"{section.group(1).strip()}\n\n{link}\n")
