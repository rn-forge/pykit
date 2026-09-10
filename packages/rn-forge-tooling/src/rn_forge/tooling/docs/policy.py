"""The repository policy the structure checks are run against.

:mod:`~rn_forge.tooling.docs.structure` knows how to check that a numbered
document series has no gaps, that a status line says something the series
allows, and that container directories and their pages are named consistently.
It must not know that the series is called ``adr``, that its numbers are four
digits, or that ``superseded by adr-0004`` is a legal status — those are one
organisation's decisions, and a general-purpose library that hardcodes them is
a library only that organisation can use (kiln ADR-0001).

So the caller supplies a :class:`DocsPolicy` describing its own conventions,
and the checks supply the mechanics. There is deliberately **no default policy
here**: a default would be exactly the hardcoded rn-forge policy this module
exists to remove, wearing a keyword argument.

This is one injected object, not a validation framework. It describes three
shapes, because three are what the checks mechanically decide:

- a **numbered series** — gapless numbers, one status line per page;
- a **sequence area** — numbered sibling directories, each with an index;
- a **nested area** — named container directories holding named pages.

An organisation with none of these passes a policy with none of them set, and
the naming and link checks still run.

Example — the policy an rn-forge repository supplies::

    DocsPolicy(
        instruction_files=("CLAUDE.md", "AGENTS.md"),
        numbered=NumberedArea(
            path="adr",
            filename=re.compile(r"^(\\d{4})-[a-z0-9-]+\\.md$"),
            statuses=re.compile(r"^(proposed|accepted|deprecated|superseded by adr-\\d{4})"),
            label="ADR",
            shape="<nnnn>-<slug>.md",
        ),
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["DocsPolicy", "NestedArea", "NumberedArea", "SequenceArea", "KEBAB_NAME"]

KEBAB_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
"""Kebab-case page names — the default :attr:`DocsPolicy.page_name`.

This one *is* a default, because it is a property of readable URLs rather than
of any organisation's decision record. Override it to allow something else.
"""

STATUS_LINE = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.MULTILINE)
"""How a status is written on a page. The vocabulary is the policy's; the
syntax is Markdown's, and is a mechanic."""


@dataclass(frozen=True, slots=True)
class NumberedArea:
    """A series of numbered documents, each carrying a status line.

    Args:
        path: The series' directory, relative to the docs root.
        filename: Page-name pattern with one capturing group: the number.
        statuses: Allowed statuses, matched against the lowercased status
            value. Lowercased because a status that names another document
            (``superseded by adr-0004``) is otherwise compared case-sensitively
            against a token nobody types consistently.
        label: What the series is called, in check messages.
        shape: The naming rule in human form, in check messages.
    """

    path: str
    filename: re.Pattern[str]
    statuses: re.Pattern[str]
    label: str
    shape: str


@dataclass(frozen=True, slots=True)
class SequenceArea:
    """Numbered sibling directories, each with its own ``index.md``.

    Args:
        path: The area's directory, relative to the docs root.
        dirname: Directory-name pattern.
        shape: The naming rule in human form, in check messages.
    """

    path: str
    dirname: re.Pattern[str]
    shape: str


@dataclass(frozen=True, slots=True)
class NestedArea:
    """Named container directories holding named pages.

    Args:
        path: The area's directory, relative to the docs root.
        dirname: Container-directory name pattern.
        dir_shape: The container naming rule in human form.
        page_glob: Which pages inside a container this rule applies to.
        page_name: Page-name pattern for those pages.
        page_shape: The page naming rule in human form.
    """

    path: str
    dirname: re.Pattern[str]
    dir_shape: str
    page_glob: str
    page_name: re.Pattern[str]
    page_shape: str


@dataclass(frozen=True, slots=True)
class DocsPolicy:
    """One repository's documentation conventions.

    Args:
        instruction_files: Root instruction files, in the order they are
            looked for. At least one must exist and lead to the docs rules.
        page_name: Naming rule for ordinary content pages.
        numbered: The numbered document series, when there is one.
        sequences: Sequence areas, if any.
        nested: Nested areas, if any.
    """

    instruction_files: tuple[str, ...]
    page_name: re.Pattern[str] = KEBAB_NAME
    numbered: NumberedArea | None = None
    sequences: tuple[SequenceArea, ...] = field(
        default_factory=tuple[SequenceArea, ...]
    )
    nested: tuple[NestedArea, ...] = field(default_factory=tuple[NestedArea, ...])

    def __post_init__(self) -> None:
        if not self.instruction_files:
            raise ValueError("A docs policy needs at least one instruction file")
