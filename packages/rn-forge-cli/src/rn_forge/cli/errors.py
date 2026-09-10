"""The error-to-exit-code mapping, and the ``main()`` wrapper that applies it.

Provides:

- :class:`ExitCode` — the exit codes an ``rn-forge`` CLI uses.
- :func:`exit_code_for` — the code a given exception maps to.
- :func:`run` — invoke a Typer app and turn whatever escapes it into a
  reported error and an exit code.

Every CLI needs this and every CLI wrote it slightly differently (kiln ADR-0009):
one printed a traceback for an application error, another swallowed
``KeyboardInterrupt`` into a generic failure. The mapping is small enough that
duplicating it looks harmless and large enough that the copies disagree.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Sequence

import typer

# Typer 0.26 vendors Click, so `click.UsageError` and Typer's own are different
# classes and an `except click.UsageError` never fires. These are the ones a
# Typer command actually raises. The import is private, which is the cost of
# Typer not re-exporting them; the `typer>=0.26.8` floor is what pins it.
from typer._click.exceptions import ClickException, UsageError

from rn_forge.cli.console import console
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = ["ExitCode", "exit_code_for", "run"]

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


def exit_code_for(error: BaseException) -> int:
    """Return the exit code *error* maps to.

    A :class:`click.exceptions.Exit` or :class:`SystemExit` carries its own
    code and is honoured **as given**, even when it is not an :class:`ExitCode`
    member: a command that deliberately exits 3 means 3, and flattening that to
    a generic failure would throw away the only thing it said.
    """
    if isinstance(error, typer.Exit):
        return error.exit_code
    if isinstance(error, SystemExit):
        return 0 if error.code is None else int(error.code)
    if isinstance(error, UsageError):
        return ExitCode.USAGE
    if isinstance(error, ClickException):
        return error.exit_code
    if isinstance(error, typer.Abort | KeyboardInterrupt):
        return ExitCode.INTERRUPTED
    return ExitCode.FAILURE


def run(app: typer.Typer, args: Sequence[str] | None = None, **kwargs: Any) -> int:
    """Invoke *app*, reporting whatever escapes it, and return an exit code.

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
        return exit_code_for(exit_signal)
    except typer.Abort, KeyboardInterrupt:
        console.warning("Interrupted.")
        return ExitCode.INTERRUPTED
    except ClickException as command_line_error:
        command_line_error.show()
        return exit_code_for(command_line_error)
    except AppException as failure:
        console.error("{}", failure)
        _LOGGER.debug("Command failed", exc_info=True)
        return ExitCode.FAILURE
    except Exception as unexpected:  # noqa: BLE001 - the top-level boundary
        console.error("Unexpected error: {}", unexpected)
        _LOGGER.exception("Unhandled exception escaped the command")
        return ExitCode.FAILURE
