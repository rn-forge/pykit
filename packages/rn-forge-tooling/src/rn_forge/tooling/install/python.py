"""A product whose release is a Python package with a console script."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.runtime.subprocess import Process
from rn_forge.tooling.install.product import Link, ToolProduct

__all__ = ["PythonTool"]


@dataclass(frozen=True)
class PythonTool(ToolProduct):
    """A Python tool installed with ``uv tool install``.

    The package must declare a console script named :attr:`name`, and that
    script must be a Typer (or Click) command: the build asks it for its zsh
    completion script. ``uv`` must be on ``PATH``; it is a program, not a
    dependency.
    """

    def artifacts(self) -> Sequence[Link]:
        """The links ``bin/<name>`` to the console script and ``completions/_<name>``."""
        return (
            Link(f"bin/{self.name}", f"bin/{self.name}"),
            Link(f"completions/_{self.name}", f"completions/_{self.name}"),
        )

    def preflight(self) -> None:
        """Refuse the install when ``uv`` is not on ``PATH``.

        Raises:
            AppException: ``uv`` was not found.
        """
        if shutil.which("uv") is None:
            raise AppException(
                "{} needs uv on PATH to install; install uv first", self.name
            )

    def build(self, release_root: Path, version_dir: Path) -> None:
        """Install the package at *release_root* into *version_dir*.

        The console script ends up at ``<version_dir>/bin/<name>`` and its zsh
        completion script at ``<version_dir>/completions/_<name>``.

        Raises:
            AppException: ``uv tool install`` failed, or the command did not
                answer the completion variable with a zsh completion script.
        """
        # uv creates version_dir itself; the environment is built in place
        # because its scripts hold absolute paths.
        env = {
            **os.environ,
            "UV_TOOL_DIR": str(version_dir / "tool"),
            "UV_TOOL_BIN_DIR": str(version_dir / "bin"),
        }
        Process.execute(
            "uv tool install", "uv", "tool", "install", str(release_root), env=env
        )
        self._write_completion(version_dir)

    def _write_completion(self, version_dir: Path) -> None:
        """Write the command's zsh completion script under *version_dir*.

        Raises:
            AppException: The command failed, or its output is not a zsh
                completion script that registers a function with ``compdef``.
        """
        var = f"_{self.name.upper().replace('-', '_')}_COMPLETE"
        result = Process.execute(
            "completion script",
            str(version_dir / "bin" / self.name),
            env={**os.environ, var: "source_zsh"},
        )
        # compinit reads only a file's first line for #compdef, and Typer's
        # output starts with a blank line.
        script = (result.stdout or "").lstrip("\n")
        lines = script.splitlines()
        if not lines or lines[0] != f"#compdef {self.name}":
            raise AppException(
                "{} did not print a zsh completion script for {}; "
                "it must be a Typer or Click command",
                self.name,
                var,
            )
        match = re.search(
            rf"^compdef (\S+) {re.escape(self.name)}$", script, re.MULTILINE
        )
        if match is None:
            raise AppException(
                "{} printed a zsh completion script for {} without a compdef line",
                self.name,
                var,
            )
        # Autoloaded, the script only defines the function and registers it, so
        # the first <TAB> completes nothing unless the function runs once.
        directory = version_dir / "completions"
        directory.mkdir(parents=True, exist_ok=True)
        PathUtils.atomic_write(
            script.rstrip("\n") + f'\n{match.group(1)} "$@"\n',
            directory / f"_{self.name}",
        )
