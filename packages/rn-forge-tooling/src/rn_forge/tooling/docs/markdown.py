"""The small amount of Markdown parsing the docs checkers agree on.

Links, headings and MkDocs-compatible anchor slugs. Deliberately regex-based
rather than a Markdown parser: the checkers need link targets and heading
anchors out of otherwise-arbitrary prose, and a full parse would make the
result depend on which extensions the site happens to enable.
"""

from __future__ import annotations

import re

__all__ = [
    "headings",
    "is_external",
    "links",
    "slugify",
    "strip_fenced_code",
]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+)$")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)

_SLUGIFY_STRIP_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUGIFY_HYPHENATE_RE = re.compile(r"[-\s]+")


def strip_fenced_code(text: str) -> str:
    """Return *text* with fenced code blocks removed.

    A link inside a code fence is an example, not a reference, and must not be
    resolved.
    """
    return FENCED_CODE_RE.sub("", text)


def slugify(heading_text: str) -> str:
    """Slugify a heading the way MkDocs/python-markdown's ``toc`` does.

    Close enough for anchor-link checking: lowercase, drop punctuation other
    than word characters, hyphens and whitespace, collapse the rest to a
    single ``-``.
    """
    text = heading_text.strip().lower()
    text = _SLUGIFY_STRIP_RE.sub("", text)
    text = _SLUGIFY_HYPHENATE_RE.sub("-", text)
    return text.strip("-")


def headings(text: str) -> set[str]:
    """Return every heading in *text* as an anchor slug."""
    return {
        slugify(match.group(2).strip())
        for line in text.splitlines()
        if (match := HEADING_RE.match(line))
    }


def links(text: str) -> list[str]:
    """Return every inline Markdown link target in *text*, in order."""
    return [match.group(1) for match in LINK_RE.finditer(strip_fenced_code(text))]


def is_external(link: str) -> bool:
    """Whether *link* points outside the docs tree and is not ours to resolve."""
    return link.startswith(("http://", "https://", "mailto:"))
