"""Public API for ``rn_forge.cli``.

The command-line layer every ``rn-forge`` application shares: the Typer
application factory, the standard option set, the console conventions and the
error-to-exit-code mapping. A repository takes its whole command-line shape
from here rather than assembling one::

    from rn_forge.cli import AppConsole, build_app, command_options, run

    app = build_app("golden-app", "Do the thing.")

    def main() -> int:
        return run(app)

Or, one level up, it declares the shape instead of writing it — see
:mod:`rn_forge.cli.declare`.

**Where this sits.** :mod:`rn_forge.commons` is runtime-neutral: safe in a web
server, a worker or a container. This package is the *process and command-line*
shape, which an ordinary batch application wants just as much as a developer
tool does — that is why it is not part of ``rn-forge-tooling``, which owns
files, installs and rendering. Nothing here imports ``rn-forge-tooling``, and
that is an enforced import contract, not a convention.

:mod:`rn_forge.cli.declare` is deliberately absent from this curated surface
and imported directly: it reads a repository's configuration document, which
is a level of coupling a caller should have to ask for by name.
"""

from rn_forge.cli.app import build_app
from rn_forge.cli.console import AppConsole, OutputMode, console
from rn_forge.cli.errors import ExitCode, exit_code_for, run
from rn_forge.cli.options import (
    CliOptions,
    DryRunOption,
    JsonOption,
    LogFileOption,
    LogLevel,
    LogLevelOption,
    QuietOption,
    YesOption,
    command_options,
    options,
    parse_key_values,
    parse_overrides,
)

__all__ = [
    "AppConsole",
    "CliOptions",
    "DryRunOption",
    "ExitCode",
    "JsonOption",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "OutputMode",
    "QuietOption",
    "YesOption",
    "build_app",
    "command_options",
    "console",
    "exit_code_for",
    "options",
    "parse_key_values",
    "parse_overrides",
    "run",
]
