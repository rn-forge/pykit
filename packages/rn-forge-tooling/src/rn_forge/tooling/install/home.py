"""Filesystem layout and activation for installed tools."""

from __future__ import annotations

import os
import re
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.locks import DirectoryLock, atomic_symlink

__all__ = ["DEFAULT_RNF_HOME", "RNF_HOME_ENV", "ToolHome", "rnf_home"]

RNF_HOME_ENV = "RNF_HOME"
"""The environment variable that relocates every installed tool."""

DEFAULT_RNF_HOME = "~/.rn-forge"
"""The home used when :data:`RNF_HOME_ENV` is unset or empty."""

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
"""A product name or version: one path segment that cannot climb out of its parent."""


def rnf_home() -> Path:
    """Return ``$RNF_HOME``, or ``~/.rn-forge`` when it is unset or empty."""
    return Path(os.environ.get(RNF_HOME_ENV) or DEFAULT_RNF_HOME).expanduser()


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
    def state_path(self) -> Path:
        """``<home>/<product>/state.json``."""
        return self.product_dir / "state.json"

    @property
    def work_dir(self) -> Path:
        """Scratch space for a transaction in flight; removed when it finishes."""
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
