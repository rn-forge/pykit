"""Tests for rn_forge.tooling.cli.lifecycle, mounted through a declared [lifecycle]."""

from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

from rn_forge.cli import ExitCode
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.runtime.console import OutputMode, console
from rn_forge.tooling.cli.lifecycle import build_tool_app, lifecycle_commands
from rn_forge.tooling.install import Link, ToolProduct


class GoldenTool(ToolProduct):
    def artifacts(self):
        return (Link("bin/golden-tool", "bin/golden-tool"),)

    def checks(self):
        return (lambda home: [Finding("golden.config", Severity.INFO, "config ok")],)


PRODUCT = GoldenTool(name="golden-tool", version="1.0.0", repo="rn-forge/golden-tool")

sys.modules.setdefault("rn_forge_tooling_test_lifecycle", sys.modules[__name__])
HERE = "rn_forge_tooling_test_lifecycle"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("RNF_HOME", str(tmp_path / "home"))
    mode = console.mode
    yield
    console.set_mode(mode)


def app(verbs=None, namespace=None):
    declared = {"product": f"{HERE}:PRODUCT"}
    if verbs is not None:
        declared["verbs"] = verbs
    if namespace is not None:
        declared["namespace"] = namespace
    return build_tool_app({"cli": {"name": "golden-tool"}, "lifecycle": declared})


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


def test_a_document_with_no_lifecycle_table_builds_a_plain_app():
    plain = build_tool_app({"cli": {"name": "golden-tool"}})
    assert plain.run(["doctor"]) == ExitCode.USAGE


def test_verbs_are_mounted_under_a_namespace(capsys):
    mounted = app(verbs=["status", "doctor"], namespace="self")
    assert mounted.run(["self", "doctor"]) == ExitCode.OK
    assert "golden.config" in capsys.readouterr().out
    assert mounted.run(["doctor"]) == ExitCode.USAGE


def test_a_namespaced_verb_may_share_a_root_command_name(capsys):
    mounted = build_tool_app(
        {
            "cli": {
                "name": "golden-tool",
                "commands": [{"name": "doctor", "target": f"{HERE}:greet"}],
            },
            "lifecycle": {
                "product": f"{HERE}:PRODUCT",
                "namespace": "self",
                "verbs": ["doctor"],
            },
        }
    )
    assert mounted.run(["self", "doctor"]) == ExitCode.OK
    assert "golden.config" in capsys.readouterr().out
    assert mounted.run(["doctor"]) == ExitCode.OK
    assert "hello" in capsys.readouterr().out


def test_a_namespace_colliding_with_a_command_is_rejected():
    with pytest.raises(AppException, match="Duplicate"):
        build_tool_app(
            {
                "cli": {
                    "name": "golden-tool",
                    "commands": [{"name": "self", "target": f"{HERE}:greet"}],
                },
                "lifecycle": {"product": f"{HERE}:PRODUCT", "namespace": "self"},
            }
        )


def test_a_verb_colliding_with_a_command_is_rejected():
    with pytest.raises(AppException, match="Duplicate"):
        build_tool_app(
            {
                "cli": {
                    "name": "golden-tool",
                    "commands": [{"name": "status", "target": f"{HERE}:greet"}],
                },
                "lifecycle": {"product": f"{HERE}:PRODUCT"},
            }
        )


@pytest.mark.parametrize("namespace", ["", "  ", "a b"])
def test_a_blank_namespace_is_rejected(namespace):
    with pytest.raises(AppException):
        app(namespace=namespace)


def test_an_unimportable_product_is_reported():
    with pytest.raises(AppException, match="lifecycle product"):
        build_tool_app(
            {
                "cli": {"name": "golden-tool"},
                "lifecycle": {"product": "no.such.module:PRODUCT"},
            }
        )


def greet(name: str = "world") -> None:
    """Greet someone, for a root command sharing a verb's name."""
    print(f"hello {name}")
