"""Tests for the rn-forge home's env.sh: the template, its writer and the hint."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from rn_forge.tooling.install.home import (
    ENV_SCHEMA,
    ENV_TEMPLATE,
    EnvWrite,
    ToolHome,
    env_hint,
    env_schema,
    render_env,
    write_env,
)

HOME_PAGE = Path(__file__).parents[2] / "docs/guides/home.md"
OLD = "# rn-forge home environment, schema {}. Written by a test.\nmarker\n"


def test_the_layout_names_env_and_completions(tmp_path):
    home = ToolHome("tool", tmp_path)
    assert home.env_path == tmp_path / "env.sh"
    assert home.completions_dir == tmp_path / "completions"
    assert ENV_SCHEMA == 1
    assert "<home>" in ENV_TEMPLATE


def test_env_template_matches_the_contract_page(tmp_path):
    blocks = re.findall(r"```sh\n(.*?)```", HOME_PAGE.read_text(), re.DOTALL)
    assert len(blocks) == 1
    page = textwrap.dedent(blocks[0]).replace("<home>", str(tmp_path))
    assert page == render_env(tmp_path)


def test_write_env_writes_a_missing_file(tmp_path):
    root = tmp_path / "home"
    assert write_env(root) is EnvWrite.WRITTEN
    assert (root / "env.sh").read_text() == render_env(root)


def test_write_env_rewrites_schema_0(tmp_path):
    (tmp_path / "env.sh").write_text(OLD.format(0))
    assert write_env(tmp_path) is EnvWrite.WRITTEN
    assert (tmp_path / "env.sh").read_text() == render_env(tmp_path)


@pytest.mark.parametrize("schema", [1, 2])
def test_write_env_leaves_a_current_or_newer_schema(tmp_path, schema):
    path = tmp_path / "env.sh"
    path.write_text(OLD.format(schema))
    assert write_env(tmp_path) is EnvWrite.CURRENT
    assert path.read_text() == OLD.format(schema)


def test_write_env_leaves_a_foreign_file(tmp_path):
    path = tmp_path / "env.sh"
    path.write_text("export FOO=1\n")
    assert write_env(tmp_path) is EnvWrite.FOREIGN
    assert path.read_text() == "export FOO=1\n"


def test_env_hint_when_bin_is_off_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))
    assert env_hint(tmp_path) == (
        f"{tmp_path}/bin is not on PATH. To use it in this shell, run:\n"
        f'  source "{tmp_path}/env.sh"\n'
        "and add that line to your shell's rc file, before compinit."
    )


def test_no_env_hint_when_bin_is_on_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", f"{tmp_path}/bin/"]))
    assert env_hint(tmp_path) is None


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_sourcing_env_sh_in_zsh(tmp_path):
    write_env(tmp_path)
    script = (
        f'source "{tmp_path}/env.sh"; source "{tmp_path}/env.sh"; '
        'print -r -- "$PATH"; print -r -- "$fpath[1]"'
    )
    out = subprocess.run(
        ["zsh", "-f", "-c", script],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert out[0].split(":").count(f"{tmp_path}/bin") == 1
    assert out[1] == f"{tmp_path}/completions"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
def test_sourcing_env_sh_in_bash(tmp_path):
    write_env(tmp_path)
    result = subprocess.run(
        ["bash", "-c", f'source "{tmp_path}/env.sh"; echo "$PATH"'],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"{tmp_path}/bin" in result.stdout.strip().split(":")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, None),
        ("", None),
        ("export FOO=1\n", None),
        (render_env(Path("/h")), 1),
        (OLD.format(2), 2),
    ],
    ids=["missing", "empty", "foreign", "rendered", "schema-2"],
)
def test_env_schema_reads_the_first_line(tmp_path, content, expected):
    if content is not None:
        (tmp_path / "env.sh").write_text(content)
    assert env_schema(tmp_path) == expected
