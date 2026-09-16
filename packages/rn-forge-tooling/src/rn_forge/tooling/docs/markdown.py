"""Markdown link, heading, and anchor parsing for documentation checks."""

from __future__ import annotations

import re

from markdown.extensions.toc import slugify as _toc_slugify
from markdown.extensions.toc import unique as _toc_unique

__all__ = [
    "headings",
    "is_external",
    "links",
    "slugify",
    "strip_fenced_code",
]

INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
"""``[text](target)``."""

REFERENCE_USE_RE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
"""``[text][label]``, and the collapsed ``[label][]``."""

REFERENCE_DEF_RE = re.compile(
    r"^[ ]{0,3}\[([^\]]+)\]:[ \t]*<?([^\s>]+)>?", re.MULTILINE
)
"""``[label]: target``, the definition a reference link resolves through."""

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*$")
FENCED_CODE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[^\n]*\n"
    r".*?"
    r"^(?P=indent)(?P=fence)`*~*[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
"""An opening fence through its matching closing fence, at the same indent.

The closing fence may be longer than the opening one, which is why the
back-reference is followed by more fence characters rather than anchored to
the exact run length."""

SEPARATOR = "-"
"""The word separator Python-Markdown's ``toc`` extension uses by default."""


def strip_fenced_code(text: str) -> str:
    """Return *text* with fenced code blocks removed.

    A link inside a code fence is an example, not a reference, and must not be
    resolved; a ``#`` line inside one is a shell comment or a Python comment,
    not a heading, and produces no anchor.
    """
    return FENCED_CODE_RE.sub("", text)


def slugify(heading_text: str) -> str:
    """Return the anchor Python-Markdown's ``toc`` extension gives this heading."""
    return _toc_slugify(heading_text.strip(), SEPARATOR)


def headings(text: str) -> set[str]:
    """Return every heading anchor a rendered *text* would carry.

    Repeated headings get the same ``-1``, ``-2`` suffixes the renderer
    assigns, so a deliberate link to the second "Consequences" resolves.
    Headings inside fenced code are ignored: they are not headings.
    """
    seen: set[str] = set()
    for line in strip_fenced_code(text).splitlines():
        match = HEADING_RE.match(line)
        if match:
            _toc_unique(slugify(match.group(2)), seen)
    return seen


def links(text: str) -> list[str]:
    """Return every Markdown link target in *text*, in order.

    Covers inline links and reference links, resolving the latter through
    their definitions. A reference with no definition yields nothing here —
    it renders as literal text rather than as a link, so there is no target to
    check.
    """
    body = strip_fenced_code(text)
    definitions = {
        label.strip().lower(): target
        for label, target in REFERENCE_DEF_RE.findall(body)
    }
    found: list[str] = []
    for match in re.finditer(
        f"{INLINE_LINK_RE.pattern}|{REFERENCE_USE_RE.pattern}", body
    ):
        inline, ref_text, label = match.group(1), match.group(2), match.group(3)
        if inline is not None:
            found.append(inline)
            continue
        key = (label or ref_text).strip().lower()
        if key in definitions:
            found.append(definitions[key])
    return found


def is_external(link: str) -> bool:
    """Whether *link* points outside the docs tree and is not ours to resolve."""
    return link.startswith(("http://", "https://", "mailto:"))
