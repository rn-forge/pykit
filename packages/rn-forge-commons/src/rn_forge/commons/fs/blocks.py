"""Managed blocks: one owner's fenced region inside a file another owner writes.

Provides :class:`ManagedBlock`, the mechanism behind ``.gitignore``'s
``# BEGIN rn-forge kiln`` section, ``CLAUDE.md``'s
``<!-- BEGIN rn-forge kiln -->`` section and ``mkdocs.yml``'s
``# BEGIN generated nav`` section: a generator owns the bytes between its two
markers and never touches the rest of the file.

Three tools had grown a private copy of this (agentkit's gitignore
scaffolding, taskkit's ``update_gitignore_block``, the docs ``gen_nav``
marker logic), each with its own idea of what happens when the markers are
missing, duplicated or empty. This is the one implementation.

Example::

    block = ManagedBlock("rn-forge kiln")
    text = block.render(gitignore_text, ".rn-forge/kiln/backups/\\n")
    block.extract(text)   # -> '.rn-forge/kiln/backups/\\n'
    block.remove(text)    # -> the original text
"""

from __future__ import annotations

from dataclasses import dataclass

from rn_forge.commons.exceptions import AppException

__all__ = ["ManagedBlock"]

HASH_COMMENT = "#"
"""Comment style for ``#``-commented files (``.gitignore``, YAML, TOML, Python)."""

HTML_COMMENT = "<!--"
"""Comment style for Markdown and HTML."""


def _line_ending(text: str) -> str:
    """The newline sequence *text* ends with, or ``""`` when it ends mid-line."""
    for ending in ("\r\n", "\n", "\r"):
        if text.endswith(ending):
            return ending
    return ""


def _dominant_newline(text: str) -> str:
    """The newline sequence *text* uses, defaulting to ``"\n"`` when it has none."""
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    return "\r" if "\r" in text else "\n"


def _normalize_newlines(text: str) -> str:
    """*text* with CRLF and CR line endings rewritten as LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True, slots=True)
class _Span:
    """Where a block sits in a file, as character offsets into its text.

    Offsets rather than line indices: replacing only ``[block_start,
    block_end)`` is what keeps every other byte of the file — its newline
    sequences and its terminal newline (or lack of one) — exactly as it was.
    """

    block_start: int
    """Offset of the first character of the begin-marker line."""
    body_start: int
    """Offset just past the begin-marker line, where the body starts."""
    body_end: int
    """Offset of the first character of the end-marker line."""
    block_end: int
    """Offset just past the end-marker line, where the file's tail resumes."""
    newline: str
    """The newline sequence the block's own lines are terminated with."""
    terminator: str
    """What follows the end marker — ``""`` when it is an unterminated last line."""


@dataclass(frozen=True, slots=True)
class ManagedBlock:
    """A named, fenced region of a file owned by one generator.

    Args:
        name: The block's name, appearing in both markers. Two blocks in one
            file must not share a name.
        comment: ``"#"`` for hash-commented formats (the default) or
            ``"<!--"`` for Markdown/HTML.
        indent: Leading whitespace the markers carry, for formats where the
            block sits inside an indented structure (``mkdocs.yml``'s ``nav:``
            uses two spaces). Applied to the markers only; the body is
            inserted as given.
    """

    name: str
    comment: str = HASH_COMMENT
    indent: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ManagedBlock name cannot be empty")
        if self.comment not in (HASH_COMMENT, HTML_COMMENT):
            raise ValueError(
                f"Unsupported comment style {self.comment!r}: "
                f"expected {HASH_COMMENT!r} or {HTML_COMMENT!r}"
            )

    @property
    def begin(self) -> str:
        """The opening marker line, without its trailing newline."""
        return self._marker("BEGIN")

    @property
    def end(self) -> str:
        """The closing marker line, without its trailing newline."""
        return self._marker("END")

    def _marker(self, keyword: str) -> str:
        if self.comment == HTML_COMMENT:
            return f"{self.indent}<!-- {keyword} {self.name} -->"
        return f"{self.indent}# {keyword} {self.name}"

    def _locate(self, text: str) -> _Span | None:
        """Return the block's :class:`_Span` in *text*, or ``None`` when absent.

        Raises:
            AppException: A marker appears more than once, or one marker is
                present without the other — both mean a hand-edited file whose
                intent cannot be guessed.
        """
        lines = text.splitlines(keepends=True)
        offsets: list[int] = []
        position = 0
        for line in lines:
            offsets.append(position)
            position += len(line)

        begin_marker = self.begin.strip()
        end_marker = self.end.strip()
        begins = [i for i, line in enumerate(lines) if line.strip() == begin_marker]
        ends = [i for i, line in enumerate(lines) if line.strip() == end_marker]
        if not begins and not ends:
            return None
        if len(begins) != 1 or len(ends) != 1:
            raise AppException(
                "Block {!r} is malformed: found {} begin and {} end markers",
                self.name,
                len(begins),
                len(ends),
            )
        if ends[0] < begins[0]:
            raise AppException(
                "Block {!r} is malformed: end marker precedes begin marker", self.name
            )
        begin, end = begins[0], ends[0]
        return _Span(
            block_start=offsets[begin],
            body_start=offsets[begin] + len(lines[begin]),
            body_end=offsets[end],
            block_end=offsets[end] + len(lines[end]),
            newline=_line_ending(lines[begin]) or _dominant_newline(text),
            terminator=_line_ending(lines[end]),
        )

    def extract(self, text: str) -> str | None:
        """Return the block's body, or ``None`` when the block is absent.

        The body is everything strictly between the markers (``""`` for an
        empty block), with the file's newline sequence normalised to ``"\n"``
        so that it compares equal to freshly rendered content regardless of how
        the file on disk is terminated.

        Raises:
            AppException: The markers are malformed (see :meth:`render`).
        """
        span = self._locate(text)
        if span is None:
            return None
        return _normalize_newlines(text[span.body_start : span.body_end])

    def render(self, text: str, body: str) -> str:
        """Return *text* with the block's body replaced by *body*.

        When the block is absent it is appended to the end of *text*, separated
        by a blank line. Everything outside the markers is preserved byte for
        byte: the surrounding text keeps its own newline sequences, its
        indentation and its lack (or presence) of a terminal newline. Inside
        the markers the generator owns the bytes, so *body* is re-terminated
        with the newline sequence the file itself uses.

        Raises:
            AppException: A marker appears more than once, one marker is
                present without the other, or they appear in the wrong order.
        """
        span = self._locate(text)
        if span is None:
            newline = _dominant_newline(text)
            prefix = text
            if prefix and _line_ending(prefix) == "":
                prefix += newline
            if prefix.strip():
                prefix += newline
            return prefix + self._block_text(body, newline, newline)
        return (
            text[: span.block_start]
            + self._block_text(body, span.newline, span.terminator)
            + text[span.block_end :]
        )

    def _block_text(self, body: str, newline: str, terminator: str) -> str:
        """The fenced block — markers plus *body* — as it is written to a file."""
        lines = [self.begin, *body.splitlines(), self.end]
        return newline.join(lines) + terminator

    def remove(self, text: str) -> str:
        """Return *text* with the block and its markers removed.

        A single blank line left immediately before the removed block is
        dropped with it — that is the separator :meth:`render` inserts, so
        repeated render/remove cycles do not accumulate whitespace. Any
        further blank lines were the file's own and are kept. Returns *text*
        unchanged when the block is absent.

        Raises:
            AppException: The markers are malformed (see :meth:`render`).
        """
        span = self._locate(text)
        if span is None:
            return text
        head = text[: span.block_start]
        head_lines = head.splitlines(keepends=True)
        if head_lines and not head_lines[-1].strip():
            head_lines.pop()
        return "".join(head_lines) + text[span.block_end :]
