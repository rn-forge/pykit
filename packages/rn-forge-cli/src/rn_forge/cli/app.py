"""Typer application setup and error-to-exit-code handling."""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Any, Mapping, Self, Sequence

import typer

# Typer 0.26 vendors Click, so `click.UsageError` and Typer's own are different
# classes and an `except click.UsageError` never fires. These are the ones a
# Typer command actually raises. The import is private, which is the cost of
# Typer not re-exporting them; the `typer>=0.26.8` floor is what pins it.
from typer._click.exceptions import ClickException, UsageError

from rn_forge.cli.options import (
    CliOptions,
    JsonOption,
    LogFileOption,
    LogLevel,
    LogLevelOption,
    QuietOption,
)
from rn_forge.cli.surface import SURFACE_KEY, CliSurface, CommandSurface
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.runtime.console import console

__all__ = ["CliApp", "ExitCode", "run"]

_LOGGER = AppLogger.get_logger(__name__)


class ExitCode(IntEnum):
    """Exit codes returned by an ``rn-forge`` CLI."""

    OK = 0
    """The command succeeded."""
    FAILURE = 1
    """The command ran and failed — the ordinary error exit."""
    USAGE = 2
    """The command line itself was wrong: an unknown flag, a bad value."""
    INTERRUPTED = 130
    """The user interrupted the command (``128 + SIGINT``)."""

    @classmethod
    def for_error(cls, error: BaseException) -> int:
        """Return the exit code *error* maps to.

        Explicit exit signals retain their supplied code, including codes not
        represented by :class:`ExitCode`.
        """
        if isinstance(error, typer.Exit):
            return error.exit_code
        if isinstance(error, SystemExit):
            return 0 if error.code is None else int(error.code)
        if isinstance(error, UsageError):
            return cls.USAGE
        if isinstance(error, ClickException):
            return error.exit_code
        if isinstance(error, typer.Abort | KeyboardInterrupt):
            return cls.INTERRUPTED
        return cls.FAILURE


def run(app: typer.Typer, args: Sequence[str] | None = None, **kwargs: Any) -> int:
    """Invoke *app*, reporting whatever escapes it, and return an exit code.

    Diagnosed :class:`~rn_forge.commons.exceptions.AppException` instances are
    reported without a traceback; unexpected exceptions are logged in full.

    Args:
        app: The Typer application to run.
        args: The command line, defaulting to ``sys.argv[1:]``.
        **kwargs: Forwarded to the underlying Click command.

    Returns:
        The exit code to hand to :func:`sys.exit`.
    """
    command = typer.main.get_command(app)
    try:
        # `standalone_mode=False` stops Click from printing and exiting on its
        # own, so the codes below are the only ones this process can produce.
        # In that mode Click *returns* the code an explicit exit asked for.
        result = command(args=args, standalone_mode=False, **kwargs)
        return result if isinstance(result, int) else ExitCode.OK
    except (typer.Exit, SystemExit) as exit_signal:
        return ExitCode.for_error(exit_signal)
    except typer.Abort, KeyboardInterrupt:
        console.warning("Interrupted.")
        return ExitCode.INTERRUPTED
    except ClickException as command_line_error:
        command_line_error.show()
        return ExitCode.for_error(command_line_error)
    except AppException as failure:
        # `.message`, not `str(failure)`: AppException's __str__ is the
        # diagnostic form (`-1 | text | {}`), which is right for a log line and
        # wrong for the one sentence a person reads on their terminal.
        console.error("{}", failure.message)
        _LOGGER.debug("Command failed", exc_info=True)
        return ExitCode.FAILURE
    except Exception as unexpected:  # noqa: BLE001 - the top-level boundary
        console.error("Unexpected error: {}", unexpected)
        _LOGGER.exception("Unhandled exception escaped the command")
        return ExitCode.FAILURE


class CliApp(typer.Typer):
    """Typer application with standard logging, output, and exit handling.

    Construct one directly, or build it from a repository's declared ``[cli]``
    surface::

        app = CliApp("golden-app", "Do the thing.")            # explicit
        app = CliApp.from_config(Path(__file__).parent / "config.toml")

    Either way the root callback already takes ``--log-level``/``--log-file``
    and ``--quiet``/``--json``, and :meth:`__call__` returns a mapped exit code
    — so ``[project.scripts]`` needs nothing but ``mypkg.cli:app``, with no
    ``main()``.

    Typer is inherited rather than wrapped, so ``@app.command()``,
    ``add_typer`` and the full constructor keyword set remain available.
    """

    def __init__(
        self,
        name: str,
        help: str | None = None,  # noqa: A002
        *,
        default_log_level: LogLevel = LogLevel.VERBOSE,
        **typer_kwargs: Any,
    ) -> None:
        """Initialize the application and register its root callback.

        ``no_args_is_help=True`` and ``pretty_exceptions_show_locals=False``
        are set by default and may be overridden through *typer_kwargs*.

        Args:
            name: The app name, also used (lowercased, spaces replaced with
                ``_``) as the root logger name.
            help: The app's ``--help`` description.
            default_log_level: Default value for ``--log-level``.
            **typer_kwargs: Forwarded to the :class:`typer.Typer` constructor.
        """
        typer_kwargs.setdefault("no_args_is_help", True)
        typer_kwargs.setdefault("pretty_exceptions_show_locals", False)
        super().__init__(name=name, help=help, **typer_kwargs)
        self._logger_name = name.replace(" ", "_").lower()

        @self.callback()
        def _root(
            ctx: typer.Context,
            log_level: LogLevelOption = default_log_level,
            log_file: LogFileOption = None,
            quiet: QuietOption = False,
            json_output: JsonOption = False,
        ) -> None:
            # `--json` needs no special handling for logging: AppLogger sends
            # console records to stderr, so a stdout payload stays parseable
            # whatever the level is and wherever on the command line it was
            # given.
            CliOptions(quiet=quiet, json_output=json_output).apply(ctx)
            AppLogger.initialize(
                root_logger_name=self._logger_name,
                level=log_level.to_int(),
                file=str(log_file) if log_file else None,
            )

    @classmethod
    def from_config(
        cls,
        source: str | Path | Mapping[str, Any],
        *,
        key: str = SURFACE_KEY,
        **typer_kwargs: Any,
    ) -> Self:
        """Build the application a repository's ``[cli]`` table describes.

        Args:
            source: A path to the configuration document, or an already-parsed
                mapping. See :meth:`CliSurface.load`.
            key: The table the surface lives under.
            **typer_kwargs: Forwarded to the constructor.

        Raises:
            AppException: The document has no surface table, a declared value
                has the wrong type, or a command's target cannot be imported.
        """
        return cls.from_surface(CliSurface.load(source, key=key), **typer_kwargs)

    @classmethod
    def from_surface(cls, surface: CliSurface, **typer_kwargs: Any) -> Self:
        """Build the application an already-parsed *surface* describes."""
        app = cls(
            surface.name,
            surface.help,
            default_log_level=surface.default_log_level,
            **typer_kwargs,
        )
        for command in surface.commands:
            app.add_declared(command)
        _LOGGER.verbose(
            "CliApp: built {} with {} command(s)",
            surface.name,
            len(surface.commands),
        )
        return app

    def add_declared(self, command: CommandSurface) -> None:
        """Attach one declared command or namespace, importing its target by name.

        Raises:
            AppException: The target cannot be imported, or is neither a
                :class:`typer.Typer` nor callable.
        """
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
            self.add_typer(target, name=command.name, help=command.help)
            return
        if not callable(target):
            raise AppException(
                "Command {!r} target {!r} is neither a Typer app nor callable",
                command.name,
                command.target,
            )
        self.command(name=command.name, help=command.help)(target)

    def run(self, args: Sequence[str] | None = None, **kwargs: Any) -> int:
        """Invoke this application and return its exit code. See :func:`run`."""
        return run(self, args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        """Invoke the application and return its exit code.

        Unlike :meth:`typer.Typer.__call__`, which runs Click in standalone
        mode and raises :exc:`SystemExit`, this returns the code — so a
        generated console script (``sys.exit(app())``) gets the mapping in
        :func:`run` for free.
        """
        return self.run(*args, **kwargs)
