"""The application class, and the error-to-exit-code mapping it runs under.

Provides:

- :class:`CliApp` — a :class:`typer.Typer` subclass whose root callback wires
  ``--log-level``/``--log-file`` into :meth:`AppLogger.initialize` and
  ``--quiet``/``--json`` into the shared
  :data:`~rn_forge.commons.runtime.console.console`, and which builds itself
  from a declared ``[cli]`` surface via :meth:`CliApp.from_config`.
- :class:`ExitCode` — the exit codes an ``rn-forge`` CLI returns.
- :func:`run` — invoke *any* Typer app and turn whatever escapes it into a
  reported error and an exit code.

**Why a subclass rather than a factory.** A console script generated from
``[project.scripts]`` is literally ``sys.exit(app())``, and
:meth:`CliApp.__call__` returns an exit code — so a repository that writes the
ordinary ``mypkg.cli:app`` entry point gets the error mapping without knowing
it exists. kiln ADR-0009 says a repo never writes exit-code handling; a
factory can only *offer* that, and the one CLI in this workspace proved the
point by shipping a bare Typer app and silently losing the mapping.

Every CLI needs this mapping and every CLI wrote it slightly differently
(ADR-0009): one printed a traceback for an application error, another
swallowed ``KeyboardInterrupt`` into a generic failure. It is small enough
that duplicating it looks harmless and large enough that the copies disagree.
"""

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
from rn_forge.cli.surface import (
    SURFACE_KEY,
    CliSurface,
    CommandSurface,
    LifecycleSurface,
)
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.runtime.console import console

__all__ = ["CliApp", "ExitCode", "run"]

_LOGGER = AppLogger.get_logger(__name__)


class ExitCode(IntEnum):
    """Exit codes an ``rn-forge`` CLI returns.

    ``USAGE`` and ``INTERRUPTED`` are not ours to choose: ``2`` is what Click
    already returns for a bad invocation, and ``130`` is the shell's
    convention for a process killed by ``SIGINT``. A wrapper script checking
    for either would be wrong if we renumbered them.
    """

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

        A :class:`click.exceptions.Exit` or :class:`SystemExit` carries its own
        code and is honoured **as given**, even when it is not an
        :class:`ExitCode` member: a command that deliberately exits 3 means 3,
        and flattening that to a generic failure would throw away the only
        thing it said.
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

    Takes any :class:`typer.Typer`, not only a :class:`CliApp` — a repository
    that dropped down to constructing its own application still gets the
    mapping, which is what ADR-0009's escape hatch means by "the same
    primitives". A :class:`CliApp` calls this for you.

    An :class:`~rn_forge.commons.exceptions.AppException` is a diagnosed
    failure: it prints as one line, with the traceback logged at debug level
    for whoever asked for one. Anything else is a defect in the command, and
    its traceback is logged in full — losing the stack of an unexpected error
    is what makes a CLI hard to debug from a bug report.

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
    """The Typer application every ``rn-forge`` CLI is.

    Construct one directly for full control, or build it from a repository's
    declared ``[cli]`` surface::

        app = CliApp("golden-app", "Do the thing.")        # explicit
        app = CliApp.from_config(".rn-forge/kiln/config.toml")  # declared

    Either way the root callback already takes ``--log-level``/``--log-file``
    and ``--quiet``/``--json``, and ``sys.exit(app())`` produces a mapped exit
    code — so ``[project.scripts]`` needs nothing but ``mypkg.cli:app``.

    The underlying Typer is not wrapped but *inherited*, so every Typer
    facility (``@app.command()``, ``app.add_typer``, the constructor's full
    keyword set) is reachable unchanged.
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
        are set by default (overridable via *typer_kwargs*) — the latter for
        the same credential-leak reason :meth:`AppLogger.initialize`'s
        ``rich_tracebacks`` defaults to ``show_locals=False``.

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

        The one-liner a repository's ``main`` module is expected to contain::

            app = CliApp.from_config(Path(__file__).parent / "config.toml")

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
        if surface.lifecycle is not None:
            app.add_lifecycle(surface.lifecycle)
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

    def add_lifecycle(self, lifecycle: LifecycleSurface) -> None:
        """Mount the declared lifecycle verbs at the root of this application.

        Imports the product and the factory by name, calls
        ``factory(product, verbs)``, and merges the :class:`typer.Typer` it
        returns into this one — so the verbs are ``golden-tool doctor``, not
        a namespace. Knowing the factory only by name is what keeps this
        package from importing the tooling that implements it.

        Raises:
            AppException: Either import fails, the factory is not callable,
                or it does not return a :class:`typer.Typer`.
        """
        imported: list[Any] = []
        for role, reference in (
            ("product", lifecycle.product),
            ("target", lifecycle.target),
        ):
            try:
                imported.append(AppUtils.import_string(reference))
            except Exception as error:
                raise AppException(
                    "Cannot import lifecycle {} {!r}: {}", role, reference, error
                ) from error
        product, factory = imported
        if not callable(factory):
            raise AppException(
                "Lifecycle target {!r} is not callable", lifecycle.target
            )
        commands = factory(product, lifecycle.verbs)
        if not isinstance(commands, typer.Typer):
            raise AppException(
                "Lifecycle target {!r} returned {!r}, not a Typer app",
                lifecycle.target,
                commands,
            )
        self.add_typer(commands)

    def run(self, args: Sequence[str] | None = None, **kwargs: Any) -> int:
        """Invoke this application and return its exit code. See :func:`run`."""
        return run(self, args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        """Return an exit code rather than raising, so ``sys.exit(app())`` works.

        This is the one place :class:`CliApp` changes an inherited behaviour
        rather than adding to it: ``typer.Typer.__call__`` runs Click in
        standalone mode, which prints and raises :exc:`SystemExit`. Returning
        the code instead is what lets a repository's ``[project.scripts]``
        entry point be the plain ``mypkg.cli:app`` and still get the mapping
        in :func:`run` — the generated console script is ``sys.exit(app())``.
        """
        return self.run(*args, **kwargs)
