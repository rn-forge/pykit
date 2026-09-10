"""Build a Typer application from a declared ``[cli]`` surface (kiln ADR-0009).

A repository describes what its command line *is* — its name, its help text,
which standard option groups it takes and which command namespaces exist — and
this module constructs the application from that description. The repository
writes command functions; it never writes app construction, flag plumbing or
exit-code handling.

The description looks like this, in whatever configuration document the
repository already has (``.rn-forge/kiln/config.toml``, for a kiln-managed
repo)::

    [cli]
    name = "golden-app"
    help = "Do the thing."
    log_options = true
    output_options = true

    [[cli.commands]]
    name = "sync"
    target = "golden_app.commands.sync:sync"

    [[cli.commands]]
    name = "db"
    help = "Database maintenance."
    target = "golden_app.commands.db:app"

A *target* naming a :class:`typer.Typer` becomes a subcommand namespace
(``app.add_typer``); a target naming a function becomes a single command
(``app.command``). Either way the target is imported by name, so this module
never learns what a command does.

**This reads a surface; it does not own one.** The ``[cli]`` table is the
repository's config, rendered there by whatever tool manages the repository.
Nothing here knows about kiln, archetypes or ``.rn-forge/`` — pass the path,
or pass the already-parsed mapping.

The escape hatch is always open: a repository whose application this cannot
describe calls :func:`~rn_forge.cli.app.build_app` and constructs its own,
using the same primitives. Dropping down costs nothing and is not a fork.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import typer

from rn_forge.cli.app import build_app
from rn_forge.cli.options import LogLevel
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.logging import AppLogger

__all__ = [
    "CliSurface",
    "CommandSurface",
    "build_declared_app",
    "declare",
    "load_surface",
]

_LOGGER = AppLogger.get_logger(__name__)

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
        log_options: Whether the app takes ``--log-level``/``--log-file``.
        output_options: Whether the app takes ``--quiet``/``--json``.
        default_log_level: The default value of ``--log-level``.
        commands: The commands and namespaces the app exposes.
    """

    name: str
    help: str | None = None
    log_options: bool = True
    output_options: bool = True
    default_log_level: LogLevel = LogLevel.VERBOSE
    commands: tuple[CommandSurface, ...] = field(
        default_factory=tuple[CommandSurface, ...]
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A declared CLI needs a name")
        duplicates = _duplicates(command.name for command in self.commands)
        if duplicates:
            raise ValueError(f"Duplicate command name(s): {', '.join(duplicates)}")


def _duplicates(names: Iterable[str]) -> list[str]:
    """Names appearing more than once, in first-seen order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated


def load_surface(
    source: str | Path | Mapping[str, Any], *, key: str = SURFACE_KEY
) -> CliSurface:
    """Read a :class:`CliSurface` from a config document or an in-memory mapping.

    Args:
        source: A path to a TOML/YAML/JSON document, or an already-parsed
            mapping. Either may be the whole document (with the surface under
            *key*) or the surface table itself.
        key: The table the surface lives under. Ignored when *source* is
            already the surface table.

    Returns:
        The parsed surface.

    Raises:
        AppException: The document has no *key* table.
    """
    data = dict(source) if isinstance(source, Mapping) else DocumentUtils.read(source)
    if key in data:
        data = data[key]
    elif "name" not in data:
        raise AppException("No [{}] table to build a CLI from", key)
    return CliSurface.from_dict(dict(data))


def build_declared_app(surface: CliSurface, **typer_kwargs: Any) -> typer.Typer:
    """Build the Typer application *surface* describes.

    Args:
        surface: The declared surface.
        **typer_kwargs: Forwarded to :func:`~rn_forge.cli.app.build_app`.

    Returns:
        The application, with every declared command registered.

    Raises:
        AppException: A command's target cannot be imported, or is neither a
            :class:`typer.Typer` nor callable.
    """
    app = build_app(
        surface.name,
        surface.help,
        add_log_options=surface.log_options,
        add_output_options=surface.output_options,
        default_log_level=surface.default_log_level,
        **typer_kwargs,
    )
    for command in surface.commands:
        _register(app, command)
    _LOGGER.verbose(
        "declare: built {} with {} command(s)", surface.name, len(surface.commands)
    )
    return app


def _register(app: typer.Typer, command: CommandSurface) -> None:
    """Attach one declared command (or namespace) to *app*."""
    try:
        target = AppUtils.import_string(command.target)
    except Exception as error:
        raise AppException(
            "Cannot import command {!r} from {!r}: {}",
            command.name,
            command.target,
            error,
        ) from error
    if isinstance(target, typer.Typer):
        app.add_typer(target, name=command.name, help=command.help)
        return
    if not callable(target):
        raise AppException(
            "Command {!r} target {!r} is neither a Typer app nor callable",
            command.name,
            command.target,
        )
    app.command(name=command.name, help=command.help)(target)


def declare(
    source: str | Path | Mapping[str, Any],
    *,
    key: str = SURFACE_KEY,
    **typer_kwargs: Any,
) -> typer.Typer:
    """Load a surface and build its application in one call.

    The one-liner a repository's ``main`` module is expected to contain::

        app = declare(Path(__file__).parent.parent / ".rn-forge/kiln/config.toml")
    """
    return build_declared_app(load_surface(source, key=key), **typer_kwargs)
