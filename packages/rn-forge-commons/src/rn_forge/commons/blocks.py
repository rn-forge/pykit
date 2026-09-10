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

    def _locate(self, text: str) -> tuple[int, int] | None:
        """Return the ``(begin, end)`` line indices of the block, or ``None``.

        Raises:
            AppException: A marker appears more than once, or one marker is
                present without the other — both mean a hand-edited file whose
                intent cannot be guessed.
        """
        lines = text.splitlines()
        begins = [
            i for i, line in enumerate(lines) if line.strip() == self.begin.strip()
        ]
        ends = [i for i, line in enumerate(lines) if line.strip() == self.end.strip()]
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
        return begins[0], ends[0]

    def extract(self, text: str) -> str | None:
        """Return the block's body, or ``None`` when the block is absent.

        The body is everything strictly between the markers, newline-terminated
        (``""`` for an empty block).

        Raises:
            AppException: The markers are malformed (see :meth:`render`).
        """
        located = self._locate(text)
        if located is None:
            return None
        begin, end = located
        body_lines = text.splitlines()[begin + 1 : end]
        return "".join(f"{line}\n" for line in body_lines)

    def render(self, text: str, body: str) -> str:
        """Return *text* with the block's body replaced by *body*.

        When the block is absent it is appended to the end of *text*, separated
        by a blank line. Everything outside the markers is preserved byte for
        byte.

        Raises:
            AppException: A marker appears more than once, one marker is
                present without the other, or they appear in the wrong order.
        """
        body_lines = body.splitlines()
        block_lines = [self.begin, *body_lines, self.end]
        located = self._locate(text)
        if located is None:
            prefix = text
            if prefix and not prefix.endswith("\n"):
                prefix += "\n"
            if prefix.strip():
                prefix += "\n"
            return prefix + "\n".join(block_lines) + "\n"
        begin, end = located
        lines = text.splitlines()
        return "\n".join(lines[:begin] + block_lines + lines[end + 1 :]) + "\n"

    def remove(self, text: str) -> str:
        """Return *text* with the block and its markers removed.

        A blank line left immediately before the removed block is dropped with
        it, so repeated render/remove cycles do not accumulate whitespace.
        Returns *text* unchanged when the block is absent.

        Raises:
            AppException: The markers are malformed (see :meth:`render`).
        """
        located = self._locate(text)
        if located is None:
            return text
        begin, end = located
        lines = text.splitlines()
        head = lines[:begin]
        while head and not head[-1].strip():
            head.pop()
        tail = lines[end + 1 :]
        remaining = head + tail
        if not remaining:
            return ""
        return "\n".join(remaining) + "\n"
