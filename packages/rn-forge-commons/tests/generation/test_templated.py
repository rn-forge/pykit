"""Tests for rn_forge.commons.generation.templated."""

from __future__ import annotations

import pytest

pytest.importorskip("jinja2")

from rn_forge.commons.fs.blocks import ManagedBlock  # noqa: E402
from rn_forge.commons.generation import ArtifactKind  # noqa: E402
from rn_forge.commons.generation.templated import (  # noqa: E402
    TemplateArtifact,
    render_artifacts,
)
from rn_forge.commons.text.templates import RenderError, TemplateEngine  # noqa: E402


def test_template_defaults_to_path_plus_j2(tmp_path):
    (tmp_path / "Taskfile.yml.j2").write_text("name: {{ name }}\n")
    engine = TemplateEngine(directory=str(tmp_path))
    [artifact] = render_artifacts(
        engine, {"name": "demo"}, [TemplateArtifact("Taskfile.yml")]
    )
    assert artifact.path == "Taskfile.yml"
    assert artifact.kind is ArtifactKind.MANAGED
    assert artifact.content == "name: demo\n"


def test_explicit_template_kind_and_block_pass_through(tmp_path):
    (tmp_path / "ignore.j2").write_text(".out/\n")
    engine = TemplateEngine(directory=str(tmp_path))
    block = ManagedBlock("tool")
    [artifact] = render_artifacts(
        engine,
        {},
        [
            TemplateArtifact(
                ".gitignore", ArtifactKind.BLOCK, template="ignore.j2", block=block
            )
        ],
    )
    assert artifact.kind is ArtifactKind.BLOCK
    assert artifact.block == block
    assert artifact.content == ".out/\n"


def test_disabled_entries_are_skipped_and_order_is_kept(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.txt.j2").write_text(name)
    engine = TemplateEngine(directory=str(tmp_path))
    artifacts = render_artifacts(
        engine,
        {},
        [
            TemplateArtifact("c.txt"),
            TemplateArtifact("b.txt", enabled=False),
            TemplateArtifact("a.txt"),
        ],
    )
    assert [a.path for a in artifacts] == ["c.txt", "a.txt"]


def test_entry_context_replaces_shared_context(tmp_path):
    (tmp_path / "x.txt.j2").write_text("{{ v }}")
    engine = TemplateEngine(directory=str(tmp_path))
    artifacts = render_artifacts(
        engine,
        {"v": "shared"},
        [TemplateArtifact("x.txt"), TemplateArtifact("x.txt", context={"v": "own"})],
    )
    assert [a.content for a in artifacts] == ["shared", "own"]


def test_render_error_names_the_path(tmp_path):
    engine = TemplateEngine(directory=str(tmp_path))
    artifacts = [TemplateArtifact("docs/x.md")]
    with pytest.raises(RenderError) as info:
        render_artifacts(engine, {}, artifacts)
    assert info.value.message.startswith("docs/x.md: ")
