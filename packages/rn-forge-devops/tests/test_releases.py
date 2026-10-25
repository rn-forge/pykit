"""Tests for the GitHub Releases adapter."""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any

import pytest

from rn_forge.devops import releases
from rn_forge.devops.index import ReleaseFile


def _asset(name: str, digest: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "browser_download_url": f"https://dl/{name}",
        "digest": digest,
    }


def _release(
    tag: str, assets: list[dict[str, Any]], *, draft: bool = False, pre: bool = False
) -> dict[str, Any]:
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "assets": assets}


def _stub_gh(
    monkeypatch: pytest.MonkeyPatch, pages: list[list[dict[str, Any]]]
) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(pages), "")

    monkeypatch.setattr(releases.subprocess, "run", run)
    return calls


def test_keeps_published_package_distributions_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        [
            _release(
                "rn-forge-commons-v0.7.0",
                [
                    _asset("rn_forge_commons-0.7.0-py3-none-any.whl", "sha256:aa"),
                    _asset("rn_forge_commons-0.7.0.tar.gz", "sha256:bb"),
                    _asset("notes.txt", "sha256:cc"),
                ],
            ),
            _release("rn-forge-web-v0.1.0", [_asset("w.whl", "sha256:dd")], draft=True),
        ],
        [
            _release("rn-forge-web-v0.2.0", [_asset("w2.whl", "sha256:ee")], pre=True),
            _release("v1.0.0", [_asset("x.whl", "sha256:ff")]),
        ],
    ]
    calls = _stub_gh(monkeypatch, pages)
    assert releases.release_files("o/r") == [
        ReleaseFile(
            "rn-forge-commons",
            "rn_forge_commons-0.7.0-py3-none-any.whl",
            "https://dl/rn_forge_commons-0.7.0-py3-none-any.whl",
            "aa",
        ),
        ReleaseFile(
            "rn-forge-commons",
            "rn_forge_commons-0.7.0.tar.gz",
            "https://dl/rn_forge_commons-0.7.0.tar.gz",
            "bb",
        ),
    ]
    assert calls[0][:3] == ["gh", "api", "repos/o/r/releases"]


def test_hashes_the_download_when_the_asset_has_no_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_gh(monkeypatch, [[_release("rn-forge-web-v0.1.0", [_asset("w.whl")])]])

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"wheel"

    monkeypatch.setattr(releases.urllib.request, "urlopen", lambda _url: _Response())
    [file] = releases.release_files("o/r")
    assert file.sha256 == hashlib.sha256(b"wheel").hexdigest()
