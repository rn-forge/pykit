"""Filesystem layout and activation for installed tools."""

from __future__ import annotations

import os
import re
from enum import StrEnum
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.locks import DirectoryLock, atomic_symlink
from rn_forge.commons.fs.paths import PathUtils

__all__ = [
    "DEFAULT_RNF_HOME",
    "ENV_SCHEMA",
    "ENV_TEMPLATE",
    "RNF_HOME_ENV",
    "EnvWrite",
    "ToolHome",
    "env_hint",
    "env_schema",
    "render_env",
    "rnf_home",
    "write_env",
]

RNF_HOME_ENV = "RNF_HOME"
"""The environment variable that relocates every installed tool."""

DEFAULT_RNF_HOME = "~/.rn-forge"
"""The home used when :data:`RNF_HOME_ENV` is unset or empty."""

ENV_SCHEMA = 1
"""The schema number of the ``env.sh`` this package writes."""

ENV_TEMPLATE = """\
# rn-forge home environment, schema 1. Written by rn-forge installers; do not edit.
# Source it from your shell's rc file, before compinit: source "<home>/env.sh"
export RNF_HOME="<home>"
case ":${PATH}:" in
  *":${RNF_HOME}/bin:"*) ;;
  *) export PATH="${RNF_HOME}/bin:${PATH}" ;;
esac
if [ -n "${ZSH_VERSION:-}" ]; then
  fpath=("${RNF_HOME}/completions" "${fpath[@]}")
fi
"""
"""The ``env.sh`` text, with ``<home>`` standing for the home's absolute path."""

_SCHEMA_LINE = re.compile(r"^# rn-forge home environment, schema (\d+)\.")

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
"""A product name or version: one path segment that cannot climb out of its parent."""


def rnf_home() -> Path:
    """Return ``$RNF_HOME``, or ``~/.rn-forge`` when it is unset or empty."""
    return Path(os.environ.get(RNF_HOME_ENV) or DEFAULT_RNF_HOME).expanduser()


class EnvWrite(StrEnum):
    """What :func:`write_env` did."""

    WRITTEN = "written"
    """The file was missing or older, and was written."""

    CURRENT = "current"
    """The file has the same or a newer schema, and was left alone."""

    FOREIGN = "foreign"
    """The file has no schema line, so it is not ours, and was left alone."""


def render_env(root: Path) -> str:
    """Return :data:`ENV_TEMPLATE` for the home at *root*, as an absolute path."""
    return ENV_TEMPLATE.replace("<home>", str(Path(root).expanduser().absolute()))


def env_schema(root: Path) -> int | None:
    """Return the schema number on the first line of ``<root>/env.sh``.

    Returns:
        The number, or ``None`` when the file is missing or empty, or its first
        line is not the schema line, so the file is not ours.
    """
    path = Path(root) / "env.sh"
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found = _SCHEMA_LINE.match(lines[0]) if lines else None
    return int(found.group(1)) if found else None


def write_env(root: Path) -> EnvWrite:
    """Write ``<root>/env.sh`` when it is missing or names a lower schema.

    Args:
        root: The home directory; created when absent.

    Returns:
        Which case applied. A file with the same or a higher schema, or with no
        schema line, is left unchanged.
    """
    path = Path(root) / "env.sh"
    if path.is_file():
        recorded = env_schema(root)
        if recorded is None:
            return EnvWrite.FOREIGN
        if recorded >= ENV_SCHEMA:
            return EnvWrite.CURRENT
    path.parent.mkdir(parents=True, exist_ok=True)
    PathUtils.atomic_write(render_env(root), path)
    return EnvWrite.WRITTEN


def env_hint(root: Path) -> str | None:
    """Return how to source ``env.sh``, or ``None`` when ``<root>/bin`` is on ``PATH``."""
    bin_dir = os.path.abspath(Path(root) / "bin")
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if any(os.path.abspath(entry) == bin_dir for entry in entries):
        return None
    home = Path(root).expanduser().absolute()
    return (
        f"{home}/bin is not on PATH. To use it in this shell, run:\n"
        f'  source "{home}/env.sh"\n'
        "and add that line to your shell's rc file, before compinit."
    )


def _segment(value: str, what: str) -> str:
    """Return *value* unchanged, or raise if it is not a single safe path segment."""
    if not _SEGMENT.match(value):
        raise AppException(
            "Invalid {} {!r}: must be a single path segment", what, value
        )
    return value


class ToolHome:
    """The on-disk layout of one product under ``$RNF_HOME``."""

    def __init__(self, name: str, root: str | Path | None = None) -> None:
        """Initialize :class:`ToolHome`.

        Args:
            name: The product name; its directory under *root*.
            root: The home directory. Defaults to :func:`rnf_home`, resolved
                now rather than per access, so one instance never straddles a
                change to the environment.

        Raises:
            AppException: *name* is not a single path segment.
        """
        self.name = _segment(name, "product name")
        self.root = Path(root).expanduser() if root is not None else rnf_home()

    @property
    def product_dir(self) -> Path:
        """``<home>/<product>/``."""
        return self.root / self.name

    @property
    def versions_dir(self) -> Path:
        """``<home>/<product>/versions/``."""
        return self.product_dir / "versions"

    @property
    def current(self) -> Path:
        """The ``current`` symlink. May not exist."""
        return self.product_dir / "current"

    @property
    def env_path(self) -> Path:
        """``<home>/env.sh``, owned by the home rather than the product."""
        return self.root / "env.sh"

    @property
    def completions_dir(self) -> Path:
        """``<home>/completions/``."""
        return self.root / "completions"

    @property
    def state_path(self) -> Path:
        """``<home>/<product>/state.json``."""
        return self.product_dir / "state.json"

    @property
    def work_dir(self) -> Path:
        """Scratch space holding unique transaction directories.

        A failed restoration retains its displaced version here; cleanup keeps it.
        """
        return self.product_dir / ".work"

    def version_dir(self, version: str) -> Path:
        """``<home>/<product>/versions/<version>/``.

        Raises:
            AppException: *version* is not a single path segment — a release
                source is remote input, and ``../..`` is a version string too.
        """
        return self.versions_dir / _segment(version, "version")

    def current_version(self) -> str | None:
        """The version ``current`` points at, or ``None`` when there is no link."""
        if not self.current.is_symlink():
            return None
        return Path(os.readlink(self.current)).name

    def installed_versions(self) -> list[str]:
        """Every version directory present, in name order."""
        if not self.versions_dir.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.versions_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    def lock(self, *, timeout: float = 30.0) -> DirectoryLock:
        """The lock every lifecycle verb that writes holds for its whole duration."""
        return DirectoryLock(self.product_dir / ".lock", timeout=timeout)

    def activate(self, version: str) -> None:
        """Point ``current`` at *version*, atomically.

        The link is relative (``versions/<version>``), so moving the whole home
        does not break it.
        """
        self.product_dir.mkdir(parents=True, exist_ok=True)
        atomic_symlink(self.current, Path("versions") / _segment(version, "version"))
