"""Standard CLI options and value parsers."""

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
    """Resolved standard flags stored on the root ``ctx.obj``."""

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

        A flag set on either the root callback or the command is retained.

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

    Values are parsed as JSON, then as TOML scalars, and otherwise retained as
    strings. Dotted keys create nested mappings.

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
