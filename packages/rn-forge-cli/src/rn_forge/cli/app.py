"""The Typer application factory.

Provides :func:`build_app` — a :class:`typer.Typer` factory whose root
callback wires ``--log-level``/``--log-file`` into
:meth:`AppLogger.initialize` and ``--quiet``/``--json`` into the
:data:`~rn_forge.cli.console.console` singleton, so that a repository
declares its command surface instead of assembling one.

The options themselves live in :mod:`rn_forge.cli.options`; the
error-to-exit-code mapping a ``main()`` wraps this in lives in
:mod:`rn_forge.cli.errors`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from rn_forge.cli.console import OutputMode, console
from rn_forge.cli.options import (
    CliOptions,
    JsonOption,
    LogFileOption,
    LogLevel,
    LogLevelOption,
    QuietOption,
)
from rn_forge.commons.logging import AppLogger

__all__ = ["build_app"]


def _apply_root_options(
    app_name: str,
    *,
    quiet: bool,
    json_output: bool,
    log_level: LogLevel | None,
    log_file: Path | None,
) -> None:
    """Apply the standard root flags to the console and the logging config.

    ``--json`` needs no special handling for logging: :meth:`AppLogger.initialize`
    sends console log records to stderr, so a stdout payload stays parseable
    whatever the log level is and wherever on the command line the flag was
    given.
    """
    if quiet and json_output:
        raise typer.BadParameter("--quiet and --json are mutually exclusive")
    if json_output:
        console.set_mode(OutputMode.JSON)
    elif quiet:
        console.set_mode(OutputMode.QUIET)
    if log_level is None:
        return
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
    ``--quiet``/``--json`` feed the :data:`~rn_forge.cli.console.console`
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
        def _callback_log_and_output(
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
        def _callback_log_only(
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
        def _callback_output_only(
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
        def _callback_bare(
            ctx: typer.Context,
        ) -> None:
            ctx.obj = CliOptions()

    return app
