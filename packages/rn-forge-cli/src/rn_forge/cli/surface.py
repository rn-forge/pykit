"""Models for a repository's declared ``[cli]`` surface."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from rn_forge.cli.options import LogLevel
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.lang.dataclasses import StrictDataclassMixin

__all__ = [
    "SURFACE_KEY",
    "CliSurface",
    "CommandSurface",
]

SURFACE_KEY = "cli"
"""The table a declared surface is read from."""


@dataclass(frozen=True, slots=True)
class CommandSurface(StrictDataclassMixin):
    """One command or command namespace of a declared CLI.

    Args:
        name: The name the command is invoked by.
        target: Import path of the implementation, as ``module:attribute`` or
            a dotted path. A :class:`typer.Typer` becomes a namespace; a
            callable becomes a single command.
        help: Help text, used as written. Defaults to the target's
            docstring up to its first section (``Args:``, ``Raises:``, ...).
    """

    name: str
    target: str
    help: str | None = None


@dataclass(frozen=True, slots=True)
class CliSurface(StrictDataclassMixin):
    """A whole declared command line.

    Args:
        name: The application name, also used as the root logger name.
        help: The application's ``--help`` description.
        default_log_level: The default value of ``--log-level``.
        commands: The commands and namespaces the app exposes.
        distribution: The installed distribution whose version ``--version``
            prints. Without one the app has no ``--version``.
    """

    name: str
    help: str | None = None
    default_log_level: LogLevel = LogLevel.VERBOSE
    commands: tuple[CommandSurface, ...] = field(
        default_factory=tuple[CommandSurface, ...]
    )
    distribution: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AppException("A declared CLI needs a name")
        if self.distribution is not None and not self.distribution.strip():
            raise AppException("A declared CLI's distribution cannot be blank")
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
            AppException: The document has no *key* table, ``commands`` is not
                an array of tables, an entry in ``commands`` is not a table,
                a declared value does not match its field's type, or a key names no
                field.
        """
        data = (
            dict(source) if isinstance(source, Mapping) else DocumentUtils.read(source)
        )
        if key in data:
            data = data[key]
        elif "name" not in data:
            raise AppException("No [{}] table to build a CLI from", key)
        _validate_commands(data, key)
        return cls.from_dict(dict(data))


def _validate_commands(data: Mapping[str, Any], key: str) -> None:
    if "commands" not in data:
        return
    commands = data["commands"]
    entries: Iterable[object] = commands
    if not isinstance(commands, list | tuple):
        raise AppException(
            "[{}] commands must be an array of tables, not {}",
            key,
            type(commands).__name__,
        )
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise AppException(
                "[{}] commands[{}] must be a table, not {}",
                key,
                index,
                type(entry).__name__,
            )


def _duplicates(names: Iterable[str]) -> list[str]:
    """Names appearing more than once, in first-seen order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated
