"""Typer CLI helpers: reusable options, a root-callback builder, and CLI parsers.

Provides:

- :class:`LogLevel` — CLI-facing log level names, with :meth:`~LogLevel.to_int`
  mapping to the matching :class:`~rn_forge.commons.logging.AppLogger` level.
- :data:`LogLevelOption`, :data:`LogFileOption`, :data:`QuietOption`,
  :data:`JsonOption` — reusable ``Annotated`` option types.
- :class:`CliOptions` — the resolved ``--quiet``/``--json`` flags, stored on
  ``ctx.obj``.
- :func:`build_app` — a :class:`typer.Typer` factory whose root callback wires
  ``--log-level``/``--log-file`` into ``AppLogger.initialize()`` and
  ``--quiet``/``--json`` into the :data:`~rn_forge.commons.console.console`
  singleton.
- :func:`options` / :func:`command_options` — read (and, for the latter,
  merge) :class:`CliOptions` from a :class:`typer.Context`.
- :func:`parse_key_values` — flat ``KEY=VALUE`` parsing.
- :func:`parse_overrides` — dotted-path, JSON-or-TOML-scalar CLI override
  parsing, e.g. ``--set database.port=5432``.

Typer's native ``bool`` handling (``--flag``/``--no-flag``) fully replaces the
old ``BooleanAction`` argparse action — no wrapper is needed for it.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Sequence, cast

import typer

from rn_forge.commons.console import OutputMode, console
from rn_forge.commons.logging import AppLogger

__all__ = [
    "CliOptions",
    "JsonOption",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "QuietOption",
    "build_app",
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


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Resolved ``--quiet``/``--json`` flags, stored on the root ``ctx.obj``."""

    quiet: bool = False
    json_output: bool = False


def options(ctx: typer.Context) -> CliOptions:
    """Return the :class:`CliOptions` stored on the root context's ``obj``."""
    root_obj = ctx.find_root().obj
    return root_obj if isinstance(root_obj, CliOptions) else CliOptions()


def command_options(
    ctx: typer.Context, *, quiet: bool = False, json_output: bool = False
) -> CliOptions:
    """Merge command-level ``--quiet``/``--json`` flags with the root context's.

    Typer allows these flags both before and after the subcommand name; the
    root callback alone only sees the former. Call this from a command that
    declares its own :data:`QuietOption`/:data:`JsonOption` parameters to
    merge them with whatever the root callback already resolved, re-apply the
    result to :data:`~rn_forge.commons.console.console`, and persist the
    merged value back onto the root context.

    Raises:
        typer.BadParameter: Both flags are set (from either level) at once.
    """
    root_opts = options(ctx)
    merged = CliOptions(
        quiet=root_opts.quiet or quiet, json_output=root_opts.json_output or json_output
    )
    if merged.quiet and merged.json_output:
        raise typer.BadParameter("--quiet and --json are mutually exclusive")
    if merged.json_output:
        console.set_mode(OutputMode.JSON)
    elif merged.quiet:
        console.set_mode(OutputMode.QUIET)
    ctx.find_root().obj = merged
    return merged


def _apply_root_options(
    app_name: str,
    *,
    quiet: bool,
    json_output: bool,
    log_level: LogLevel | None,
    log_file: Path | None,
) -> None:
    if quiet and json_output:
        raise typer.BadParameter("--quiet and --json are mutually exclusive")
    if json_output:
        console.set_mode(OutputMode.JSON)
    elif quiet:
        console.set_mode(OutputMode.QUIET)
    if log_level is not None:
        AppLogger.initialize(
            root_logger_name=app_name.replace(" ", "_").lower(),
            level=log_level.to_int(),
            file=str(log_file) if log_file else None,
        )


def build_app(
    name: str,
    help: str | None = None,  # noqa: A002
    *,
    add_log_options: bool = True,
    add_output_options: bool = True,
    default_log_level: LogLevel = LogLevel.VERBOSE,
    **typer_kwargs: Any,
) -> typer.Typer:
    """Return a Typer app whose root callback wires the standard options.

    ``--log-level``/``--log-file`` feed :meth:`AppLogger.initialize`;
    ``--quiet``/``--json`` feed the :data:`~rn_forge.commons.console.console`
    singleton. ``no_args_is_help=True`` and ``pretty_exceptions_show_locals=False``
    are set by default (overridable via *typer_kwargs*) — the latter for the
    same credential-leak reason :meth:`AppLogger.initialize`'s
    ``rich_tracebacks`` defaults to ``show_locals=False``.

    Args:
        name: The app name, also used (lowercased, spaces replaced with ``_``)
            as the root logger name.
        help: The app's ``--help`` description.
        add_log_options: Add ``--log-level``/``--log-file``. Default ``True``.
        add_output_options: Add ``--quiet``/``--json``. Default ``True``.
        default_log_level: Default value for ``--log-level``.
        **typer_kwargs: Forwarded to the :class:`typer.Typer` constructor.

    Returns:
        A configured, ready-to-use :class:`typer.Typer` app.
    """
    typer_kwargs.setdefault("no_args_is_help", True)
    typer_kwargs.setdefault("pretty_exceptions_show_locals", False)
    app = typer.Typer(name=name, help=help, **typer_kwargs)

    if add_log_options and add_output_options:

        @app.callback()
        def _callback_log_and_output(  # pyright: ignore[reportUnusedFunction]
            ctx: typer.Context,
            log_level: LogLevelOption = default_log_level,
            log_file: LogFileOption = None,
            quiet: QuietOption = False,
            json_output: JsonOption = False,
        ) -> None:
            _apply_root_options(
                name,
                quiet=quiet,
                json_output=json_output,
                log_level=log_level,
                log_file=log_file,
            )
            ctx.obj = CliOptions(quiet=quiet, json_output=json_output)

    elif add_log_options:

        @app.callback()
        def _callback_log_only(  # pyright: ignore[reportUnusedFunction]
            ctx: typer.Context,
            log_level: LogLevelOption = default_log_level,
            log_file: LogFileOption = None,
        ) -> None:
            _apply_root_options(
                name,
                quiet=False,
                json_output=False,
                log_level=log_level,
                log_file=log_file,
            )
            ctx.obj = CliOptions()

    elif add_output_options:

        @app.callback()
        def _callback_output_only(  # pyright: ignore[reportUnusedFunction]
            ctx: typer.Context,
            quiet: QuietOption = False,
            json_output: JsonOption = False,
        ) -> None:
            _apply_root_options(
                name,
                quiet=quiet,
                json_output=json_output,
                log_level=None,
                log_file=None,
            )
            ctx.obj = CliOptions(quiet=quiet, json_output=json_output)

    else:

        @app.callback()
        def _callback_bare(  # pyright: ignore[reportUnusedFunction]
            ctx: typer.Context,
        ) -> None:
            ctx.obj = CliOptions()

    return app


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
    pairs with :meth:`rn_forge.commons.collections.DictUtils.merge`'s
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
