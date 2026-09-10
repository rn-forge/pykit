"""Classification: what applying an artifact *would* do, before anything is written.

:func:`classify` maps (rendered content, disk content, last-applied state) to
an :class:`~rn_forge.tooling.generation.artifacts.Action`. :func:`plan`
collects those into a :class:`~rn_forge.tooling.generation.artifacts.Plan`;
actions that mean "the working tree disagrees with what I last wrote" (drift,
conflict, missing) are *blocking*, and abort the whole plan before anything is
written unless the caller has explicitly approved that path.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.hashing import ContentHash

from rn_forge.tooling.generation.artifacts import (
    Action,
    Artifact,
    ArtifactKind,
    Change,
    Plan,
    StateEntry,
    block_from_entry,
    read_text,
    resolve_within,
)

__all__ = ["classify", "plan"]


def _disk_content(root: Path, artifact: Artifact) -> str | None:
    """The artifact's current content on disk (block body for a block), or ``None``."""
    path = root / artifact.path
    if not path.is_file():
        return None
    text = read_text(path)
    if artifact.block is None:
        return text
    return artifact.block.extract(text)


def classify(root: Path, artifact: Artifact, entry: StateEntry | None) -> Action:
    """Return the :class:`Action` applying *artifact* would take.

    Args:
        root: The repository root; *artifact*'s path is relative to it.
        artifact: The freshly-rendered artifact.
        entry: What was recorded the last time this artifact was applied, or
            ``None`` if it never was.
    """
    if artifact.kind is ArtifactKind.SEEDED:
        return Action.SKIP if (root / artifact.path).exists() else Action.CREATE

    disk = _disk_content(root, artifact)
    disk_hash = None if disk is None else ContentHash.of(disk)
    last_hash = entry.content_hash if entry else None
    new_hash = artifact.content_hash

    if disk is None:
        if entry is None:
            return Action.CREATE if artifact.block is None else Action.INSERT
        return Action.MISSING if artifact.block is None else Action.DRIFT
    if entry is None:
        return Action.CONFLICT
    if disk_hash != last_hash:
        return Action.DRIFT
    return Action.UNCHANGED if last_hash == new_hash else Action.UPDATE


def _stale_action(root: Path, entry: StateEntry) -> tuple[Action, Action]:
    """Classify a state entry the current render no longer produces.

    Returns:
        The classified action and the action it *intends* — the two differ
        only when the file was hand-edited: the classification is
        :attr:`Action.DRIFT` (blocking), while the intent stays the deletion
        or block removal that approving the drift should carry out.
    """
    path = root / entry.path
    if entry.kind is ArtifactKind.SEEDED or not path.is_file():
        return Action.FORGET, Action.FORGET
    if entry.kind is ArtifactKind.BLOCK:
        if entry.begin_marker is None or entry.end_marker is None:
            return Action.FORGET, Action.FORGET
        block = block_from_entry(entry)
        body = block.extract(read_text(path))
        if body is None:
            return Action.FORGET, Action.FORGET
        clean = ContentHash.of(body) == entry.content_hash
        return (Action.REMOVE if clean else Action.DRIFT), Action.REMOVE
    clean = ContentHash.of_file(path) == entry.content_hash
    return (Action.DELETE if clean else Action.DRIFT), Action.DELETE


def plan(
    root: str | Path,
    artifacts: Iterable[Artifact],
    entries: Mapping[str, StateEntry],
    *,
    force: Iterable[str] = (),
) -> Plan:
    """Classify every artifact and every stale state entry, writing nothing.

    Args:
        root: The repository root.
        artifacts: Every artifact the generators produced for this run.
        entries: The state recorded by the previous apply, keyed by
            :attr:`Artifact.key`.
        force: Repo-relative paths (or artifact keys) whose blocking action the
            caller has explicitly approved. Approving a path approves only that
            path; there is deliberately no "force everything" value here.
    """
    root = Path(root)
    approved = set(force)
    changes: list[Change] = []
    seen: set[str] = set()

    for artifact in artifacts:
        key = artifact.key
        if key in seen:
            raise AppException("Duplicate artifact key {!r}", key)
        seen.add(key)
        resolve_within(root, artifact.path)
        action = classify(root, artifact, entries.get(key))
        changes.append(
            Change(
                key=key,
                path=artifact.path,
                kind=artifact.kind,
                action=action,
                artifact=artifact,
                approved=key in approved or artifact.path in approved,
            )
        )

    for key, entry in entries.items():
        if key in seen:
            continue
        resolve_within(root, entry.path)
        action, intent = _stale_action(root, entry)
        changes.append(
            Change(
                key=key,
                path=entry.path,
                kind=entry.kind,
                action=action,
                approved=key in approved or entry.path in approved,
                intent=intent,
            )
        )

    return Plan(tuple(changes))
