"""Workstation install mechanics: a portable lock, atomic symlinks, archive extraction.

The rn-forge tools (`agentkit`, `kiln`) each install themselves into a
versioned directory under ``$RNF_HOME`` and flip a ``current`` symlink at it.
The *mechanics* of doing that safely are identical between them and are owned
here; the product coordinates — which ``$RNF_HOME``, which GitHub repository,
which retention policy — stay in each product, because their layouts differ
(``commons-upgrade-plan.md`` §18.3, §18.4).

Provides:

- :class:`DirectoryLock` — a portable, ``mkdir``-based cross-process advisory
  lock.
- :func:`atomic_symlink` — replace a symlink without ever unlinking it first.
- :func:`extract_archive` — tar/zip extraction with a safe default filter.

Deliberately absent: the download. ``urllib.request`` against a GitHub
releases API is product-specific coordinates, and a generic "download a file"
wrapper adds nothing over the standard library.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Literal, Self

from rn_forge.commons.exceptions import AppException

__all__ = ["DirectoryLock", "atomic_symlink", "extract_archive"]


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


def extract_archive(
    archive: str | Path,
    destination: str | Path,
    *,
    filter: Literal["data", "tar", "fully_trusted"] = "data",  # noqa: A002
) -> Path:
    """Extract a ``.tar``/``.zip`` *archive* into *destination*, returning its root dir.

    Args:
        archive: The archive file. Tar formats (``.tar``, ``.tar.gz``,
            ``.tar.bz2``, ...) are detected by content; anything else is
            treated as a zip.
        destination: Directory the archive's contents are extracted into.
            Created if absent.
        filter: The :func:`tarfile.TarFile.extractall` extraction filter
            (tar archives only — a tar-slip vulnerability is exactly the
            kind of thing a hand-rolled second copy of this reintroduces,
            which is the point of having it once with a safe default).
            Zip extraction has no equivalent filter parameter.

    Returns:
        The single top-level directory the archive extracted into.

    Raises:
        AppException: The archive's root does not contain exactly one
            directory.
    """
    archive = Path(archive)
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter=filter)
    else:
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(dest)
    entries = [item for item in dest.iterdir() if item.is_dir()]
    if len(entries) != 1:
        raise AppException(
            "Expected exactly one root directory in archive {}, found {}",
            archive,
            len(entries),
        )
    return entries[0]


# ---------------------------------------------------------------------------
# DirectoryLock — a portable, cross-process advisory lock
# ---------------------------------------------------------------------------


class DirectoryLock:
    """A portable advisory lock backed by ``mkdir``, for cross-process serialization.

    ``mkdir`` is atomic on every filesystem this runs on; ``flock`` is not
    available everywhere (and behaves inconsistently over network
    filesystems). Use this when the lock must actually hold across processes
    on an unknown filesystem; use :meth:`StateStore.locked
    <rn_forge.tooling.state.StateStore.locked>`'s ``flock``-based locking
    instead when a failed lock should degrade to unlocked rather than raise.

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
