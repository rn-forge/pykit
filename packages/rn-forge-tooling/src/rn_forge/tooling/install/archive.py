"""Safe extraction of single-root tar and zip release bundles."""

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
            for tar archives. Zip extraction has no equivalent parameter.

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
