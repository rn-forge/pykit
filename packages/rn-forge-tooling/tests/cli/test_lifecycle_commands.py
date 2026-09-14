"""Tests for rn_forge.tooling.cli.lifecycle, mounted through a declared [cli.lifecycle]."""

from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

from rn_forge.cli import CliApp, CliSurface, ExitCode
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.runtime.console import OutputMode, console
from rn_forge.tooling.cli.lifecycle import lifecycle_commands
from rn_forge.tooling.install import Link, ToolProduct


class GoldenTool(ToolProduct):
    def artifacts(self):
        return (Link("bin/golden-tool", "bin/golden-tool"),)

    def checks(self):
        return (lambda home: [Finding("golden.config", Severity.INFO, "config ok")],)


PRODUCT = GoldenTool(name="golden-tool", version="1.0.0", repo="rn-forge/golden-tool")

sys.modules.setdefault("rn_forge_tooling_test_lifecycle", sys.modules[__name__])
HERE = "rn_forge_tooling_test_lifecycle"
TARGET = "rn_forge.tooling.cli.lifecycle:lifecycle_commands"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("RNF_HOME", str(tmp_path / "home"))
    mode = console.mode
    yield
    console.set_mode(mode)


def app(verbs=None):
    lifecycle = {"product": f"{HERE}:PRODUCT", "target": TARGET}
    if verbs is not None:
        lifecycle["verbs"] = verbs
    return CliApp.from_surface(
        CliSurface.load({"name": "golden-tool", "lifecycle": lifecycle})
    )


def archive(tmp_path: Path, version: str) -> Path:
    path = tmp_path / f"golden-tool-{version}.tar.gz"
    payload = b"#!/bin/sh\n"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(f"golden-tool-{version}/bin/golden-tool")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return path


def test_doctor_on_a_dev_checkout_exits_zero_and_shows_the_product_check(capsys):
    assert app().run(["doctor"]) == ExitCode.OK
    assert "golden.config" in capsys.readouterr().out


def test_status_json_has_a_version(capsys):
    assert app().run(["--json", "status"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "1.0.0"
    assert payload["installed"] is None


def test_install_from_an_archive_then_doctor_and_uninstall(tmp_path, capsys):
    built = archive(tmp_path, "1.0.0")
    assert app().run(["install", "--archive", str(built), "--version", "1.0.0"]) == 0
    assert (tmp_path / "home/bin/golden-tool").is_symlink()
    assert app().run(["doctor"]) == ExitCode.OK
    assert app().run(["uninstall", "--yes"]) == ExitCode.OK
    assert not (tmp_path / "home/golden-tool").exists()


def test_archive_without_version_is_a_usage_error(tmp_path):
    assert app().run(["install", "--archive", str(tmp_path / "x")]) == ExitCode.USAGE


def test_only_the_declared_verbs_are_mounted(capsys):
    assert app(["status"]).run(["doctor"]) == ExitCode.USAGE


def test_an_unknown_verb_is_rejected():
    with pytest.raises(AppException, match="Unknown lifecycle verb"):
        lifecycle_commands(PRODUCT, ["explode"])


def test_a_non_product_is_rejected():
    with pytest.raises(AppException, match="not a ToolProduct"):
        lifecycle_commands(object(), ["status"])  # type: ignore[arg-type]
