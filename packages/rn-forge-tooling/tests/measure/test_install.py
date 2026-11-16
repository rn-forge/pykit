"""Measure a verified release install from a local archive."""

from __future__ import annotations

import io
import os
import tarfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal

import pytest
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.tooling.install import LocalArchive, ToolHome, ToolProduct, install
from rn_forge.tooling.install import release as release_module

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]

_SIZE = 64 * 1024 * 1024


def _archive(path: Path) -> None:
    payload = b"x" * _SIZE
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo("tool-1.0.0/payload")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))


def test_install(
    measure: Measure, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = tmp_path / "tool-1.0.0.tar"
    _archive(archive)
    source = LocalArchive(archive, "1.0.0", ContentHash.of_file(archive))
    counts = {"downloads": 0, "hashes": 0, "extracts": 0}

    download = LocalArchive.download

    def counted_download(local: LocalArchive, version: str, destination: Path) -> Path:
        counts["downloads"] += 1
        return download(local, version, destination)

    hash_file = ContentHash.of_file

    def counted_hash(path: str | Path, *, algorithm: str = "sha256") -> str | None:
        counts["hashes"] += 1
        return hash_file(path, algorithm=algorithm)

    extract = release_module.extract_archive

    def counted_extract(
        archive_path: str | Path,
        destination: str | Path,
        *,
        filter: Literal["data", "tar", "fully_trusted"] = "data",
    ) -> Path:
        counts["extracts"] += 1
        return extract(archive_path, destination, filter=filter)

    monkeypatch.setattr(LocalArchive, "download", counted_download)
    monkeypatch.setattr(ContentHash, "of_file", staticmethod(counted_hash))
    monkeypatch.setattr(release_module, "extract_archive", counted_extract)
    home = ToolHome("tool", tmp_path / "home")
    with measure("install_64mib", {"archive_mib": 64}, "buffering") as recorded:
        install(ToolProduct("tool", "1.0.0", release_source=source), home=home)
        recorded.update(counts)
        recorded["bytes"] = archive.stat().st_size
    assert counts == {"downloads": 1, "hashes": 1, "extracts": 1}
