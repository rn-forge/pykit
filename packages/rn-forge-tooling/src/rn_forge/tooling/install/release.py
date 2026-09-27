"""Release sources, download verification, and extraction."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.logging import AppLogger

from rn_forge.tooling.install.archive import extract_archive

__all__ = ["GitHubReleases", "LocalArchive", "ReleaseSource", "fetch_release"]

_LOGGER = AppLogger.get_logger(__name__)

_TIMEOUT = 60.0
"""Seconds before a network request to a release host is abandoned."""


@runtime_checkable
class ReleaseSource(Protocol):
    """Where a product's releases are published."""

    def latest(self) -> str:
        """Return the newest released version."""
        ...

    def download(self, version: str, destination: Path) -> Path:
        """Write the archive for *version* into the directory *destination*.

        Returns:
            The archive file.
        """
        ...

    def checksum(self, version: str) -> str | None:
        """Return the SHA-256 hex digest *version*'s archive must match, if published."""
        ...


@dataclass(frozen=True, slots=True)
class GitHubReleases:
    """Releases published as tags of a GitHub repository.

    The archive is GitHub's generated source tarball for the tag. GitHub
    publishes no checksum for those, so :meth:`checksum` returns ``None`` and
    the download is trusted to TLS; a product that attaches a checksum asset
    to its releases implements :class:`ReleaseSource` to verify it.

    Args:
        repo: ``owner/name``.
        tag_prefix: What the tag carries before the version — ``"v"`` for
            ``v1.2.0``, ``"golden-tool-v"`` in a monorepo.
        api_url: The GitHub API root, for GitHub Enterprise.
        web_url: The GitHub web root the tarball is served from.
    """

    repo: str
    tag_prefix: str = "v"
    api_url: str = "https://api.github.com"
    web_url: str = "https://github.com"

    def latest(self) -> str:
        """Return the version of the repository's latest release.

        Raises:
            AppException: The request failed, or the latest release's tag does
                not carry :attr:`tag_prefix`.
        """
        url = f"{self.api_url}/repos/{self.repo}/releases/latest"
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:  # noqa: S310 - https coordinates from the product
                tag = str(json.load(response).get("tag_name") or "")
        except (urllib.error.URLError, ValueError) as error:
            raise AppException(
                "Cannot resolve the latest release of {}: {}", self.repo, error
            ) from error
        if not tag.startswith(self.tag_prefix) or tag == self.tag_prefix:
            raise AppException(
                "Latest release tag {!r} of {} does not start with {!r}",
                tag,
                self.repo,
                self.tag_prefix,
            )
        return tag.removeprefix(self.tag_prefix)

    def download(self, version: str, destination: Path) -> Path:
        """Download the tag's source tarball into *destination*.

        Raises:
            AppException: The download failed.
        """
        tag = f"{self.tag_prefix}{version}"
        url = f"{self.web_url}/{self.repo}/archive/refs/tags/{tag}.tar.gz"
        archive = destination / f"{tag}.tar.gz"
        try:
            with (
                urllib.request.urlopen(url, timeout=_TIMEOUT) as response,  # noqa: S310 - https coordinates from the product
                archive.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
        except urllib.error.URLError as error:
            raise AppException("Cannot download {}: {}", url, error) from error
        return archive

    def checksum(self, version: str) -> str | None:
        """``None``: GitHub publishes no checksum for a generated tarball."""
        return None


@dataclass(frozen=True, slots=True)
class LocalArchive:
    """One archive already on disk, standing in for a release.

    Args:
        path: The archive file.
        version: The version the archive holds. Not inferred from its
            contents: reading a version out of a tree is the product's
            convention, not this module's.
        sha256: The digest to verify against, when known.
    """

    path: Path
    version: str
    sha256: str | None = None

    def latest(self) -> str:
        """The archive's own version — it is the only one there is."""
        return self.version

    def download(self, version: str, destination: Path) -> Path:
        """Copy the archive into *destination*.

        Raises:
            AppException: *version* is not the archive's, or the file is missing.
        """
        if version != self.version:
            raise AppException(
                "{} holds version {}, not {}", self.path, self.version, version
            )
        if not self.path.is_file():
            raise AppException("Archive not found: {}", self.path)
        return Path(shutil.copy2(self.path, destination / self.path.name))

    def checksum(self, version: str) -> str | None:
        """The digest given at construction, if any."""
        return self.sha256


def fetch_release(source: ReleaseSource, version: str, workdir: str | Path) -> Path:
    """Download *version* from *source* into *workdir*, verify it, and extract it.

    Args:
        source: Where the release is published.
        version: The version to fetch.
        workdir: A scratch directory; created if absent. The archive and its
            extracted tree are left here for the caller to clean up.

    Returns:
        The archive's single root directory.

    Raises:
        AppException: The download failed, the archive does not match the
            published checksum, or it does not have exactly one root directory.
    """
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    archive = source.download(version, work)
    expected = source.checksum(version)
    if expected is not None:
        actual = ContentHash.of_file(archive)
        if actual != expected.strip().lower():
            raise AppException(
                "Checksum mismatch for {}: expected {}, got {}",
                archive.name,
                expected,
                actual,
            )
    _LOGGER.verbose("install.release: fetched {} into {}", version, work)
    return extract_archive(archive, work / "extracted")
