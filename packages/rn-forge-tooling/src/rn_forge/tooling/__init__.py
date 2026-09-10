"""Public API for ``rn_forge.tooling``.

The shared developer-tooling surface for the ``rn-forge-*`` command-line tools.
A repository takes its whole CLI/console/state layer from here rather than
assembling one::

    from rn_forge.tooling import AppConsole, build_app, command_options

    app = build_app("kiln", "Generate and check repository standards.")

Where :mod:`rn_forge.commons` is runtime-neutral — safe in a web server, a
worker or a container — this package is deliberately workstation-shaped: it
assumes a terminal, a developer's filesystem and a tool that writes files.
A package that ships into a deployed runtime must not depend on it outside a
``codegen`` extra.

Two modules are deliberately absent from this curated surface and imported
directly: :mod:`rn_forge.tooling.docs`, whose checkers are a command's concern
rather than a library's, and :mod:`rn_forge.tooling.generation`, whose names
(``Artifact``, ``Action``, ``plan``, ``apply``) are too generic to hoist into
a package-level namespace.
"""

from rn_forge.tooling.cli import (
    CliOptions,
    DryRunOption,
    JsonOption,
    LogFileOption,
    LogLevel,
    LogLevelOption,
    QuietOption,
    YesOption,
    build_app,
    command_options,
    options,
    parse_key_values,
    parse_overrides,
)
from rn_forge.tooling.console import AppConsole, OutputMode, console
from rn_forge.tooling.install import DirectoryLock, atomic_symlink, extract_archive
from rn_forge.tooling.state import StateStore
from rn_forge.tooling.templates import RenderError, TemplateEngine

__all__ = [
    "AppConsole",
    "CliOptions",
    "DirectoryLock",
    "DryRunOption",
    "JsonOption",
    "LogFileOption",
    "LogLevel",
    "LogLevelOption",
    "OutputMode",
    "QuietOption",
    "RenderError",
    "StateStore",
    "TemplateEngine",
    "YesOption",
    "atomic_symlink",
    "build_app",
    "command_options",
    "console",
    "extract_archive",
    "options",
    "parse_key_values",
    "parse_overrides",
]
