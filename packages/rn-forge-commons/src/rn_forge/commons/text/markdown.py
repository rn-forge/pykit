"""Markdown structure: headings, anchors, links, tables and fenced code.

Documents are parsed with markdown-it-py (CommonMark plus GFM tables). Heading
anchors follow Python-Markdown's ``toc`` extension, which MkDocs uses.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from markdown.extensions.toc import slugify as _toc_slugify
from markdown.extensions.toc import unique as _toc_unique
from markdown_it import MarkdownIt
from markdown_it.token import Token

__all__ = ["MarkdownHeading", "MarkdownTable", "MarkdownUtils"]

_PARSER = MarkdownIt("commonmark").enable("table")


@dataclass(frozen=True, slots=True)
class MarkdownHeading:
    """A heading of a Markdown document.

    Attributes:
        level: The heading level, 1 to 6.
        text: The heading as plain text; inline markup is dropped and code
            spans are kept as text.
        anchor: The anchor a renderer gives the heading, unique within the
            document.
        line: The 0-based line of the heading.
    """

    level: int
    text: str
    anchor: str
    line: int


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    """A GFM pipe table of a Markdown document.

    Attributes:
        header: The header cells.
        rows: The body rows, each exactly ``len(header)`` cells.
        start: The 0-based line of the header row.
        end: The 0-based line after the last row.
    """

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    start: int
    end: int


class MarkdownUtils:
    """Read the structure of Markdown text."""

    @staticmethod
    def slugify(text: str, separator: str = "-") -> str:
        """Return the anchor slug of *text*, as Python-Markdown's ``toc`` makes it.

        Example::

            MarkdownUtils.slugify("Hello, World!")  # "hello-world"
        """
        return str(_toc_slugify(text.strip(), separator))

    @staticmethod
    def headings(text: str) -> list[MarkdownHeading]:
        """List the ATX and setext headings of *text*, in document order.

        A heading inside code is not listed. A repeated anchor gets ``_1``,
        ``_2`` and so on.
        """
        tokens = _PARSER.parse(text)
        used: set[str] = set()
        found: list[MarkdownHeading] = []
        for index, token in enumerate(tokens):
            if token.type != "heading_open" or token.map is None:
                continue
            plain = _plain_text(tokens[index + 1])
            anchor = str(_toc_unique(MarkdownUtils.slugify(plain), used))
            found.append(
                MarkdownHeading(
                    level=int(token.tag[1:]),
                    text=plain,
                    anchor=anchor,
                    line=token.map[0],
                )
            )
        return found

    @staticmethod
    def anchors(text: str) -> set[str]:
        """Return the anchors of the headings of *text*."""
        return {heading.anchor for heading in MarkdownUtils.headings(text)}

    @staticmethod
    def title(text: str) -> str | None:
        """Return the text of the first level-1 heading, or ``None``."""
        for heading in MarkdownUtils.headings(text):
            if heading.level == 1:
                return heading.text
        return None

    @staticmethod
    def links(text: str) -> list[str]:
        """List the link and image targets of *text*, in document order.

        Inline, reference, collapsed-reference and autolink targets are
        included, percent-decoded. A reference with no definition and anything
        inside code is not a link.

        Example::

            MarkdownUtils.links("[a](b%20c.md) ![i](p.png)")  # ["b c.md", "p.png"]
        """
        targets: list[str] = []
        for token in _PARSER.parse(text):
            for child in token.children or []:
                if child.type == "link_open":
                    target = child.attrGet("href")
                elif child.type == "image":
                    target = child.attrGet("src")
                else:
                    continue
                if isinstance(target, str):
                    targets.append(urllib.parse.unquote(target))
        return targets

    @staticmethod
    def is_external(link: str) -> bool:
        """Return whether *link* has a URL scheme or is scheme-relative."""
        return bool(urllib.parse.urlsplit(link).scheme) or link.startswith("//")

    @staticmethod
    def tables(text: str) -> list[MarkdownTable]:
        """List the GFM pipe tables of *text*, in document order.

        A table inside code is not listed. Cells are stripped; a short row is
        padded with empty cells to the header's width.
        """
        found: list[MarkdownTable] = []
        rows: list[list[str]] = []
        start = end = 0
        for token in _PARSER.parse(text):
            if token.type == "table_open" and token.map is not None:
                rows = []
                start, end = token.map
            elif token.type == "tr_open":
                rows.append([])
            elif token.type == "inline" and rows:
                rows[-1].append(token.content.strip())
            elif token.type == "table_close":
                width = len(rows[0])
                body = tuple(tuple((row + [""] * width)[:width]) for row in rows[1:])
                found.append(MarkdownTable(tuple(rows[0]), body, start, end))
                rows = []
        return found

    @staticmethod
    def strip_fenced_code(text: str) -> str:
        """Return *text* with every line of every fenced code block removed."""
        lines = text.splitlines(keepends=True)
        for token in _PARSER.parse(text):
            if token.type == "fence" and token.map is not None:
                first, last = token.map
                for number in range(first, last):
                    lines[number] = ""
        return "".join(lines)


def _plain_text(inline: Token) -> str:
    """Join an inline token's text and code-span children."""
    return "".join(
        child.content
        for child in inline.children or []
        if child.type in ("text", "code_inline")
    )
