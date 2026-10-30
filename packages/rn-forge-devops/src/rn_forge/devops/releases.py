"""The GitHub Releases adapter: the distribution files a repository has published."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from typing import Any

from rn_forge.devops.index import ReleaseFile

_TAG = re.compile(r"^(rn-forge-[a-z0-9-]+)-v\d+\.\d+\.\d+$")
_REPO = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*/[A-Za-z0-9_.][A-Za-z0-9_.-]*")
_SUFFIXES = (".whl", ".tar.gz")


def _releases(repo: str) -> list[dict[str, Any]]:
    # `--slurp` wraps each page in one outer array.
    result = subprocess.run(  # noqa: S603  # fixed argv, no shell
        ["gh", "api", f"repos/{repo}/releases", "--paginate", "--slurp"],  # noqa: S607  # tool resolved from PATH
        check=True,
        capture_output=True,
        text=True,
    )
    pages: list[list[dict[str, Any]]] = json.loads(result.stdout)
    return [release for page in pages for release in page]


def _sha256(asset: dict[str, Any]) -> str:
    digest: str | None = asset.get("digest")
    if digest and digest.startswith("sha256:"):
        return digest.removeprefix("sha256:")
    with urllib.request.urlopen(asset["browser_download_url"]) as response:  # noqa: S310  # asset URL comes from the GitHub API
        return hashlib.sha256(response.read()).hexdigest()


def release_files(repo: str) -> list[ReleaseFile]:
    """Return the wheels and sdists of `repo`'s published `rn-forge-*` releases.

    Drafts, prereleases and tags not named `rn-forge-<name>-vX.Y.Z` are skipped.
    A file's digest is the asset's `sha256:` digest, or the hash of its download
    when the asset has none.

    Raises:
        ValueError: If `repo` is not `owner/name`.
        subprocess.CalledProcessError: If `gh api` fails.
    """
    if not _REPO.fullmatch(repo) or {".", ".."} & set(repo.split("/")):
        raise ValueError(f"invalid repo {repo!r}")
    files: list[ReleaseFile] = []
    for release in _releases(repo):
        match = _TAG.match(release["tag_name"])
        if release["draft"] or release["prerelease"] or not match:
            continue
        files.extend(
            ReleaseFile(
                project=match.group(1),
                filename=asset["name"],
                url=asset["browser_download_url"],
                sha256=_sha256(asset),
            )
            for asset in release["assets"]
            if asset["name"].endswith(_SUFFIXES)
        )
    return files
