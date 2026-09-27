"""Models for a repository's declared ``[cli]`` surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Self

from rn_forge.cli.options import LogLevel
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.lang.dataclasses import DataclassMixin

__all__ = [
    "CliSurface",
    "CommandSurface",
    "SURFACE_KEY",
]

SURFACE_KEY = "cli"
"""The table a declared surface is read from."""


@dataclass(frozen=True, slots=True)
class CommandSurface(DataclassMixin):
    """One command or command namespace of a declared CLI.

    Args:
        name: The name the command is invoked by.
        target: Import path of the implementation, as ``module:attribute`` or
            a dotted path. A :class:`typer.Typer` becomes a namespace; a
            callable becomes a single command.
        help: Help text. Defaults to the target's own docstring, which is
            where it belongs when there is one.
    """

    name: str
    target: str
    help: str | None = None


@dataclass(frozen=True, slots=True)
class CliSurface(DataclassMixin):
    """A whole declared command line.

    Args:
        name: The application name, also used as the root logger name.
        help: The application's ``--help`` description.
        default_log_level: The default value of ``--log-level``.
        commands: The commands and namespaces the app exposes.
    """

    name: str
    help: str | None = None
    default_log_level: LogLevel = LogLevel.VERBOSE
    commands: tuple[CommandSurface, ...] = field(
        default_factory=tuple[CommandSurface, ...]
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AppException("A declared CLI needs a name")
        duplicates = _duplicates(command.name for command in self.commands)
        if duplicates:
            raise AppException("Duplicate command name(s): {}", ", ".join(duplicates))

    @classmethod
    def load(
        cls, source: str | Path | Mapping[str, Any], *, key: str = SURFACE_KEY
    ) -> Self:
        """Read a surface from a config document or an in-memory mapping.

        Args:
            source: A path to a TOML/YAML/JSON document, or an already-parsed
                mapping. Either may be the whole document (with the surface
                under *key*) or the surface table itself.
            key: The table the surface lives under. Ignored when *source* is
                already the surface table.

        Returns:
            The parsed, validated surface.

        Raises:
            AppException: The document has no *key* table, or a declared value
                does not match its field's type.
        """
        data = (
            dict(source) if isinstance(source, Mapping) else DocumentUtils.read(source)
        )
        if key in data:
            data = data[key]
        elif "name" not in data:
            raise AppException("No [{}] table to build a CLI from", key)
        return cls.from_dict(dict(data))


def _duplicates(names: Iterable[str]) -> list[str]:
    """Names appearing more than once, in first-seen order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated
