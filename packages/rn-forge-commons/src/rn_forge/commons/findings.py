"""Structured findings: the result shape every checker and doctor reports in.

Provides :class:`Finding` and :class:`Severity`. A checker returns a list of
findings; a CLI renders them as a table or, with ``--json``, as
``[finding.as_dict()]`` — :class:`Finding` is a
:class:`~rn_forge.commons.lang.dataclasses.DataclassMixin`, so that serialisation
is free and round-trips.

``code`` is the stable identifier, dotted and lowercase (``artifact.drift``,
``docs.broken-link``). It is what a suppression list, a CI annotation or a
release note refers to, so it must outlive rewording of ``message``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rn_forge.commons.lang.types import JsonValue
from rn_forge.commons.lang.dataclasses import DataclassMixin

__all__ = ["Finding", "Severity"]


class Severity(StrEnum):
    """How a finding should be treated by the command that collected it."""

    ERROR = "error"
    """The check failed; the command exits non-zero."""
    WARNING = "warning"
    """Worth reporting, but not a failure on its own."""
    INFO = "info"
    """Context for the reader; never affects an exit code."""


@dataclass(frozen=True, slots=True)
class Finding(DataclassMixin):
    """One structured result from a check.

    Args:
        code: Stable dotted identifier for the rule that produced this, e.g.
            ``"artifact.drift"``.
        severity: See :class:`Severity`.
        message: Human-readable, one line, specific to this occurrence.
        path: The path the finding is about, when there is one — relative to
            the repository for a repository check, absolute for a check of a
            workstation install.
        line: 1-indexed line within *path*, when the rule is line-precise.
        details: Rule-specific structured data for ``--json`` consumers —
            expected and actual hashes, a resolved link target, and so on.
            Never load-bearing for rendering.
    """

    code: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    details: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])

    @property
    def is_error(self) -> bool:
        """Whether this finding should fail the command that collected it."""
        return self.severity is Severity.ERROR

    def __str__(self) -> str:
        location = self.path or ""
        if location and self.line is not None:
            location = f"{location}:{self.line}"
        prefix = f"{location}: " if location else ""
        return f"{prefix}[{self.code}] {self.message}"
