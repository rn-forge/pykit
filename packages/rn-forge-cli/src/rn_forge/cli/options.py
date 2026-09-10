"""The standard option set every ``rn-forge`` CLI takes, and the CLI parsers.

Provides:

- :class:`LogLevel` — CLI-facing log level names, with :meth:`~LogLevel.to_int`
  mapping to the matching :class:`~rn_forge.commons.logging.AppLogger` level.
- :data:`LogLevelOption`, :data:`LogFileOption`, :data:`QuietOption`,
  :data:`JsonOption`, :data:`DryRunOption`, :data:`YesOption` — reusable
  ``Annotated`` option types.
- :class:`CliOptions` — the resolved ``--quiet``/``--json``/``--dry-run``/
  ``--yes`` flags, stored on ``ctx.obj``.
- :func:`options` / :func:`command_options` — read (and, for the latter,
  merge) :class:`CliOptions` from a :class:`typer.Context`.
- :func:`parse_key_values` — flat ``KEY=VALUE`` parsing.
- :func:`parse_overrides` — dotted-path, JSON-or-TOML-scalar CLI override
  parsing, e.g. ``--set database.port=5432``.

Boolean flags use Typer's native ``--flag``/``--no-flag`` handling.
The application factory that wires these into a root callback is
:func:`rn_forge.cli.app.build_app`.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Sequence, cast

import typer

from rn_forge.cli.console import OutputMode, console
from rn_forge.commons.logging import AppLogger

__all__ = [
    "CliOptions",
    "DryRunOption",
    "JsonOption",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "QuietOption",
    "YesOption",
    "command_options",
    "options",
    "parse_key_values",
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


@dataclass(frozen=True, slots=True)
class CliOptions:
    """The resolved standard flags, stored on the root ``ctx.obj``.

    ``dry_run`` and ``yes`` live here rather than on each command because
    every command that writes anything needs both, and a command reading them
    off the context cannot forget to thread one through.
    """

    quiet: bool = False
    json_output: bool = False
    dry_run: bool = False
    yes: bool = False


def options(ctx: typer.Context) -> CliOptions:
    """Return the :class:`CliOptions` stored on the root context's ``obj``."""
    root_obj = ctx.find_root().obj
    return root_obj if isinstance(root_obj, CliOptions) else CliOptions()


def command_options(
    ctx: typer.Context,
    *,
    quiet: bool = False,
    json_output: bool = False,
    dry_run: bool = False,
    yes: bool = False,
) -> CliOptions:
    """Merge command-level standard flags with the root context's.

    Typer allows these flags both before and after the subcommand name; the
    root callback alone only sees the former. Call this from a command that
    declares its own :data:`QuietOption`/:data:`JsonOption` parameters to
    merge them with whatever the root callback already resolved, re-apply the
    result to :data:`~rn_forge.cli.console.console`, and persist the
    merged value back onto the root context.

    Raises:
        typer.BadParameter: Both flags are set (from either level) at once.
    """
    root_opts = options(ctx)
    merged = CliOptions(
        quiet=root_opts.quiet or quiet,
        json_output=root_opts.json_output or json_output,
        dry_run=root_opts.dry_run or dry_run,
        yes=root_opts.yes or yes,
    )
    if merged.quiet and merged.json_output:
        raise typer.BadParameter("--quiet and --json are mutually exclusive")
    if merged.json_output:
        console.set_mode(OutputMode.JSON)
    elif merged.quiet:
        console.set_mode(OutputMode.QUIET)
    ctx.find_root().obj = merged
    return merged


def parse_key_values(values: Sequence[str] | None) -> dict[str, str]:
    """Parse ``["a=1", "b=2"]`` into ``{"a": "1", "b": "2"}``.

    Raises:
        typer.BadParameter: An entry has no ``=``.

    See Also:
        :func:`parse_overrides` — the dotted-path, typed-scalar sibling of
        this function, for ``--set dotted.key=value`` CLI overrides.
    """
    result: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise typer.BadParameter(
                f"Invalid key=value pair {item!r}. Expected format: KEY=VALUE"
            )
        key, _, val = item.partition("=")
        result[key] = val
    return result


def parse_overrides(values: Sequence[str] | None) -> dict[str, Any]:
    """Parse ``["a.b=1", "c=[1,2]"]`` into a nested mapping with typed scalars.

    Each value is parsed first as JSON, then as a TOML scalar, falling back to
    the raw string when neither succeeds. Dotted keys nest into sub-mappings —
    pairs with :meth:`rn_forge.commons.lang.collections.DictUtils.merge`'s
    ``overrides`` layer.

    Raises:
        typer.BadParameter: An entry has no ``=``, an empty key, or a dotted
            path that collides with a scalar set by an earlier entry.

    See Also:
        :func:`parse_key_values` — the flat/untyped variant.
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
