"""The standard option set every ``rn-forge`` CLI takes, and its value parsers.

Provides:

- :class:`LogLevel` — CLI-facing log level names, with :meth:`~LogLevel.to_int`
  mapping to the matching :class:`~rn_forge.commons.logging.AppLogger` level.
- :data:`LogLevelOption`, :data:`LogFileOption`, :data:`QuietOption`,
  :data:`JsonOption`, :data:`DryRunOption`, :data:`YesOption`, :data:`SetOption`
  — reusable ``Annotated`` option types.
- :class:`CliOptions` — the resolved ``--quiet``/``--json``/``--dry-run``/
  ``--yes`` flags, stored on ``ctx.obj``.
- :func:`parse_overrides` — dotted-path, JSON-or-TOML-scalar parsing for
  :data:`SetOption`, e.g. ``--set database.port=5432``.

Boolean flags use Typer's native ``--flag``/``--no-flag`` handling. The
application class that wires these into a root callback is
:class:`rn_forge.cli.app.CliApp`.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self, Sequence, cast

import typer

from rn_forge.commons.logging import AppLogger
from rn_forge.commons.runtime.console import OutputMode, console

__all__ = [
    "CliOptions",
    "DryRunOption",
    "JsonOption",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "QuietOption",
    "SetOption",
    "YesOption",
    "parse_overrides",
]


class LogLevel(StrEnum):
    """CLI-facing log level names. Values are lowercase for clean ``--help`` output."""

    CRITICAL = "critical"
    ERROR = "error"
    SUCCESS = "success"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    VERBOSE = "verbose"
    DEBUG = "debug"
    SPAM = "spam"
    TRACE = "trace"

    def to_int(self) -> int:
        """Return the matching :class:`~rn_forge.commons.logging.AppLogger` level constant."""
        mapping: dict[LogLevel, int] = {
            LogLevel.CRITICAL: AppLogger.CRITICAL,
            LogLevel.ERROR: AppLogger.ERROR,
            LogLevel.SUCCESS: AppLogger.SUCCESS,
            LogLevel.WARNING: AppLogger.WARNING,
            LogLevel.NOTICE: AppLogger.NOTICE,
            LogLevel.INFO: AppLogger.INFO,
            LogLevel.VERBOSE: AppLogger.VERBOSE,
            LogLevel.DEBUG: AppLogger.DEBUG,
            LogLevel.SPAM: AppLogger.SPAM,
            LogLevel.TRACE: AppLogger.TRACE,
        }
        return mapping[self]


LogLevelOption = Annotated[
    LogLevel, typer.Option("--log-level", "-ll", help="Logging level.")
]
LogFileOption = Annotated[
    Path | None, typer.Option("--log-file", "-lf", help="Path to a log file.")
]
QuietOption = Annotated[
    bool, typer.Option("--quiet", "-q", help="Suppress non-essential output.")
]
JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit machine-readable JSON output.")
]
DryRunOption = Annotated[
    bool,
    typer.Option(
        "--dry-run", help="Report what would change without writing anything."
    ),
]
YesOption = Annotated[
    bool, typer.Option("--yes", "-y", help="Assume yes for every confirmation.")
]
SetOption = Annotated[
    list[str] | None,
    typer.Option("--set", help="Override a config value, as dotted.key=value."),
]


@dataclass(frozen=True, slots=True)
class CliOptions:
    """The resolved standard flags, stored on the root ``ctx.obj``.

    ``dry_run`` and ``yes`` live here rather than on each command because
    every command that writes anything needs both, and a command reading them
    off the context cannot forget to thread one through.

    Build one with :meth:`from_context` and finish with :meth:`apply`::

        @app.command()
        def sync(ctx: typer.Context, quiet: QuietOption = False) -> None:
            opts = CliOptions.from_context(ctx, quiet=quiet).apply(ctx)

    The two steps are separate because :meth:`from_context` is pure and
    :meth:`apply` is not — a caller that only wants to know what the options
    *are* (a test, a command managing its own console) stops after the first.
    """

    quiet: bool = False
    json_output: bool = False
    dry_run: bool = False
    yes: bool = False

    @classmethod
    def from_context(
        cls,
        ctx: typer.Context,
        *,
        quiet: bool = False,
        json_output: bool = False,
        dry_run: bool = False,
        yes: bool = False,
    ) -> Self:
        """Return the options for this command: the root callback's, merged with these.

        Typer allows the standard flags both before and after the subcommand
        name; the root callback alone only sees the former. A command that
        declares its own :data:`QuietOption`/:data:`JsonOption` parameters
        passes them here to merge them with whatever the root already
        resolved. A flag set at either level wins.

        Pure — nothing is written to *ctx* and no console mode is changed.
        Chain :meth:`apply` for that.
        """
        root_obj = ctx.find_root().obj
        root = root_obj if isinstance(root_obj, cls) else cls()
        return replace(
            root,
            quiet=root.quiet or quiet,
            json_output=root.json_output or json_output,
            dry_run=root.dry_run or dry_run,
            yes=root.yes or yes,
        )

    def apply(self, ctx: typer.Context) -> Self:
        """Validate this combination, set the console mode, and persist onto *ctx*.

        Three effects, all of them deliberate: the mutually-exclusive pair is
        rejected, :data:`~rn_forge.commons.runtime.console.console` is switched
        to the mode the flags ask for, and the result is written to the root
        context so a nested command reads the merged value rather than the
        root callback's.

        Returns:
            ``self``, so the call chains off :meth:`from_context`.

        Raises:
            typer.BadParameter: Both ``--quiet`` and ``--json`` are set, from
                either level.
        """
        if self.quiet and self.json_output:
            raise typer.BadParameter("--quiet and --json are mutually exclusive")
        if self.json_output:
            console.set_mode(OutputMode.JSON)
        elif self.quiet:
            console.set_mode(OutputMode.QUIET)
        ctx.find_root().obj = self
        return self


def parse_overrides(values: Sequence[str] | None) -> dict[str, Any]:
    """Parse ``["a.b=1", "c=[1,2]"]`` into a nested mapping with typed scalars.

    The parser behind :data:`SetOption`. Each value is parsed first as JSON,
    then as a TOML scalar, falling back to the raw string when neither
    succeeds. Dotted keys nest into sub-mappings, which is exactly the shape
    :meth:`rn_forge.commons.lang.collections.DictUtils.merge_layers` takes as
    its highest-precedence layer — so a ``--set`` override lands in a layered
    configuration with its provenance tracked.

    Raises:
        typer.BadParameter: An entry has no ``=``, an empty key, or a dotted
            path that collides with a scalar set by an earlier entry.
    """
    result: dict[str, Any] = {}
    for expression in values or []:
        if "=" not in expression:
            raise typer.BadParameter(f"Override must be KEY=VALUE: {expression!r}")
        key, raw = expression.split("=", 1)
        parts = [part for part in key.strip().split(".") if part]
        if not parts:
            raise typer.BadParameter(f"Override key cannot be empty: {expression!r}")
        cursor: dict[str, Any] = result
        for part in parts[:-1]:
            existing: Any = cursor.setdefault(part, {})
            if not isinstance(existing, dict):
                raise typer.BadParameter(f"Override collides with scalar key: {key!r}")
            cursor = cast("dict[str, Any]", existing)
        cursor[parts[-1]] = _parse_scalar(raw)
    return result


def _parse_scalar(raw: str) -> Any:
    """Parse *raw* as JSON, then as a TOML scalar, else return it unchanged."""
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    try:
        return tomllib.loads(f"value = {stripped}\n")["value"]
    except tomllib.TOMLDecodeError, KeyError:
        return raw
