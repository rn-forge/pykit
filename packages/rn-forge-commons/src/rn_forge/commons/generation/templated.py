"""Artifacts rendered from Jinja templates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.generation.artifacts import Artifact, ArtifactKind
from rn_forge.commons.text.templates import RenderError, TemplateEngine

__all__ = ["TemplateArtifact", "render_artifacts"]


@dataclass(frozen=True, slots=True)
class TemplateArtifact:
    """One artifact to render: its path, its ownership and its template.

    Args:
        path: Repo-relative path of the rendered artifact.
        kind: Who owns its bytes; see ArtifactKind.
        template: Template name; ``None`` means ``f"{path}.j2"``.
        block: The fenced block, for an ArtifactKind.BLOCK artifact.
        enabled: ``False`` leaves the artifact out.
        context: Replaces the shared context for this artifact alone.
    """

    path: str
    kind: ArtifactKind = ArtifactKind.MANAGED
    template: str | None = None
    block: ManagedBlock | None = None
    enabled: bool = True
    context: Mapping[str, object] | None = None


def render_artifacts(
    engine: TemplateEngine,
    context: Mapping[str, object],
    artifacts: Iterable[TemplateArtifact],
) -> list[Artifact]:
    """Render each enabled artifact, in order.

    Raises:
        RenderError: A template failed; the message starts with the artifact's path.
        ValueError: From Artifact, when ``block`` does not match ``kind``.
    """
    rendered: list[Artifact] = []
    for entry in artifacts:
        if not entry.enabled:
            continue
        try:
            content = engine.render(
                entry.template or f"{entry.path}.j2",
                context if entry.context is None else entry.context,
            )
        except RenderError as exc:
            raise RenderError("{}: {}", entry.path, exc.message) from exc
        rendered.append(Artifact(entry.path, entry.kind, content, block=entry.block))
    return rendered
