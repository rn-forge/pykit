"""Archive extraction for release bundles.

Provides :func:`extract_archive` — tar/zip extraction with a safe default
filter, requiring the archive to contain exactly one root directory. That
single-root requirement is a release-bundle convention rather than a general
filesystem operation, which is why this stays in tooling while the lock and
the atomic symlink it used to sit beside moved to
:mod:`rn_forge.commons.fs.locks`.

Deliberately absent: the download. ``urllib.request`` against a GitHub
releases API is product-specific coordinates, and a generic "download a file"
wrapper adds nothing over the standard library.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Literal

from rn_forge.commons.exceptions import AppException

__all__ = ["extract_archive"]


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
