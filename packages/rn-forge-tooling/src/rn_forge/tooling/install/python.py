"""A product whose release is a Python package with a console script."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.subprocess import Process
from rn_forge.tooling.install.product import Link, ToolProduct

__all__ = ["PythonTool"]


@dataclass(frozen=True)
class PythonTool(ToolProduct):
    """A Python tool installed with ``uv tool install``.

    The package must declare a console script named :attr:`name`. ``uv`` must
    be on ``PATH``; it is a program, not a dependency.
    """

    def artifacts(self) -> Sequence[Link]:
        """The link ``bin/<name>`` to the console script."""
        return (Link(f"bin/{self.name}", f"bin/{self.name}"),)

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

        The console script ends up at ``<version_dir>/bin/<name>``.

        Raises:
            AppException: ``uv tool install`` failed.
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
