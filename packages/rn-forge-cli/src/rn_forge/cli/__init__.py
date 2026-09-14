"""Public API for ``rn_forge.cli``.

The command-line layer every ``rn-forge`` application shares: the Typer
application class, the standard option set and the error-to-exit-code mapping.
A repository takes its whole command-line shape from here rather than
assembling one::

    from rn_forge.cli import CliApp

    app = CliApp("golden-app", "Do the thing.")

    @app.command()
    def sync() -> None:
        \"\"\"Synchronise the thing.\"\"\"

and points ``[project.scripts]`` at ``golden_app.cli:app``. The generated
console script is ``sys.exit(app())``, and :meth:`CliApp.__call__` returns a
mapped exit code, so nothing in the repository handles exit codes by hand.

One level up, a repository *declares* its shape instead of writing it — a
``[cli]`` table in its own configuration document, built by
:meth:`CliApp.from_config` (kiln ADR-0009)::

    app = CliApp.from_config(".rn-forge/kiln/config.toml")

**Where this sits.** :mod:`rn_forge.commons` is runtime-neutral: safe in a web
server, a worker or a container, and it owns the console facade this package
drives. This package is the *command-line* shape, which an ordinary batch
application wants just as much as a developer tool does — that is why it is
not part of ``rn-forge-tooling``, which owns files, installs and rendering.
Nothing here imports ``rn-forge-tooling``, and that is an enforced import
contract, not a convention.
"""

from rn_forge.cli.app import CliApp, ExitCode, run
from rn_forge.cli.options import (
    CliOptions,
    DryRunOption,
    JsonOption,
    LogFileOption,
    LogLevel,
    LogLevelOption,
    QuietOption,
    SetOption,
    YesOption,
    parse_overrides,
)
from rn_forge.cli.surface import CliSurface, CommandSurface, LifecycleSurface

__all__ = [
    "CliApp",
    "CliOptions",
    "CliSurface",
    "CommandSurface",
    "DryRunOption",
    "ExitCode",
    "JsonOption",
    "LifecycleSurface",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "QuietOption",
    "SetOption",
    "YesOption",
    "parse_overrides",
    "run",
]
