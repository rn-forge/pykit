"""Cross-process serialization and atomic publication on the filesystem.

Provides:

- :class:`DirectoryLock` — a portable, ``mkdir``-based cross-process advisory
  lock.
- :func:`atomic_symlink` — replace a symlink without ever unlinking it first.

Neither carries any installer policy in its signature, which is why they live
here rather than in the tool that first needed them: a local worker can
serialize filesystem work or publish a snapshot atomically for reasons that
have nothing to do with installing a release.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Callable, Self

from rn_forge.commons.exceptions import AppException

__all__ = ["DirectoryLock", "atomic_symlink"]


def atomic_symlink(link: str | Path, target: str | Path) -> None:
    """Atomically create or replace the symlink *link*, pointing at *target*.

    Writes a temporary symlink (``.<name>.tmp-<pid>``) next to *link* and
    renames it into place with :meth:`~pathlib.Path.replace`. Never
    unlinks *link* first — that would leave a window where the link does
    not exist at all, which a concurrent reader could observe.

    Args:
        link: The symlink path to create or replace.
        target: The path the symlink should point at. Not resolved —
            pass a relative path here for a relocatable symlink.
    """
    link = Path(link)
    tmp_link = link.parent / f".{link.name}.tmp-{os.getpid()}"
    tmp_link.symlink_to(target)
    tmp_link.replace(link)


class DirectoryLock:
    """A portable advisory lock backed by ``mkdir``, for cross-process serialization.

    ``mkdir`` is atomic on every filesystem this runs on; ``flock`` is not
    available everywhere (and behaves inconsistently over network
    filesystems). Use this when the lock must actually hold across processes
    on an unknown filesystem, and something with a best-effort ``flock``
    instead when a failed lock should degrade to an unlocked write rather than
    raise.

    Example::

        with DirectoryLock(product_home / ".lock", on_wait=lambda p: print(f"waiting for {p}...")):
            ...
    """

    def __init__(
        self,
        path: str | Path,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.05,
        on_wait: Callable[[Path], None] | None = None,
    ) -> None:
        """Initialize :class:`DirectoryLock`.

        Args:
            path: The lock directory. Must not exist while the lock is held
                by anyone; created (and removed) by this lock.
            timeout: Seconds to wait for the lock before raising.
            poll_interval: Seconds between acquisition attempts.
            on_wait: Called once, with *path*, the first time acquisition has
                to wait — lets a caller print "waiting for lock ..." without
                this module importing a console.
        """
        self._path = Path(path)
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._on_wait = on_wait
        self._acquired = False

    def __enter__(self) -> Self:
        """Acquire the lock, waiting up to ``timeout`` seconds.

        Raises:
            AppException: The lock could not be acquired within ``timeout``.
        """
        deadline = time.monotonic() + self._timeout
        announced = False
        while True:
            try:
                self._path.mkdir(parents=True)
                self._acquired = True
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise AppException(
                        "Could not acquire lock within {}s: {}",
                        self._timeout,
                        self._path,
                    ) from None
                if not announced and self._on_wait is not None:
                    self._on_wait(self._path)
                    announced = True
                time.sleep(self._poll_interval)

    def __exit__(self, *exc: object) -> None:
        """Release the lock, if held."""
        if self._acquired:
            shutil.rmtree(self._path, ignore_errors=True)
