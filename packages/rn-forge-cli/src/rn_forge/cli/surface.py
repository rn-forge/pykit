"""The declared ``[cli]`` surface a repository describes itself with (kiln ADR-0009).

A repository states what its command line *is* — its name, its help text and
which command namespaces exist — and :class:`~rn_forge.cli.app.CliApp` builds
the application from that description. The repository writes command
functions; it never writes app construction, flag plumbing or exit-code
handling.

The description looks like this, in whatever configuration document the
repository already has (``.rn-forge/kiln/config.toml``, for a kiln-managed
repo)::

    [cli]
    name = "golden-app"
    help = "Do the thing."

    [[cli.commands]]
    name = "sync"
    target = "golden_app.commands.sync:sync"

    [[cli.commands]]
    name = "db"
    help = "Database maintenance."
    target = "golden_app.commands.db:app"

A *target* naming a :class:`typer.Typer` becomes a subcommand namespace; a
target naming a function becomes a single command. Either way the target is
imported by name, so nothing here learns what a command does.

**This module holds records, not behaviour.** It parses and validates a
surface; :mod:`rn_forge.cli.app` turns one into a running application. The
split is what lets a repository's configuration be *checked* — by a kiln
config command, or by a test — without constructing a Typer app to do it.

**This reads a surface; it does not own one.** The ``[cli]`` table is the
repository's config, rendered there by whatever tool manages the repository.
Nothing here knows about kiln, archetypes or ``.rn-forge/`` — pass the path,
or pass the already-parsed mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Self

from rn_forge.cli.options import LogLevel
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.lang.dataclasses import StrictDataclassMixin

__all__ = ["CliSurface", "CommandSurface", "SURFACE_KEY"]

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
        help: Help text. Defaults to the target's own docstring, which is
            where it belongs when there is one.
    """

    name: str
    target: str
    help: str | None = None


@dataclass(frozen=True, slots=True)
class CliSurface(StrictDataclassMixin):
    """A whole declared command line.

    A :class:`~rn_forge.commons.lang.dataclasses.StrictDataclassMixin` because
    every field here comes from a document a person wrote by hand: a ``str``
    where a ``bool`` belongs should name the offending key, not surface three
    frames later as an attribute error.

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
