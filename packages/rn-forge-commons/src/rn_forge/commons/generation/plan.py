"""Classify generated artifacts without modifying the working tree."""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.generation.artifacts import (
    Action,
    Artifact,
    ArtifactKind,
    Change,
    Plan,
    StateEntry,
    block_from_entry,
    canonical_values,
    disk_key_values,
    read_text,
    render_keys,
    resolve_within,
)

__all__ = ["classify", "diff", "disk_content", "plan"]


def disk_content(root: Path, artifact: Artifact) -> str | None:
    """The artifact's current content on disk (block body for a block), or ``None``."""
    path = root / artifact.path
    if not path.is_file():
        return None
    text = read_text(path)
    if artifact.block is None:
        return text
    return artifact.block.extract(text)


def diff(
    root: Path,
    change: Change,
    *,
    entries: Mapping[str, StateEntry] | None = None,
) -> str:
    """A unified diff from *change*'s content on disk to its rendered content.

    A block diffs its body; a missing file diffs from empty; a keys change
    diffs the whole file, with *entries* (the previous state) showing dropped
    paths as removed. Returns ``""`` when the change has no artifact or
    nothing differs.
    """
    artifact = change.artifact
    if artifact is None:
        return ""
    if artifact.kind is ArtifactKind.KEYS:
        disk = read_text(root / artifact.path)
        after = render_keys(root, change, entries or {})
    else:
        disk = disk_content(root, artifact) or ""
        after = artifact.content
    return "".join(
        difflib.unified_diff(
            disk.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=artifact.path,
            tofile=artifact.path,
        )
    )


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

    if artifact.kind is ArtifactKind.KEYS:
        return _classify_keys(root, artifact, entry)

    disk = disk_content(root, artifact)
    if disk is None:
        if entry is None:
            return Action.CREATE if artifact.block is None else Action.INSERT
        return Action.MISSING if artifact.block is None else Action.DRIFT
    if entry is None:
        return Action.CONFLICT
    if ContentHash.of(disk) != entry.content_hash:
        return Action.DRIFT
    return (
        Action.UNCHANGED
        if entry.content_hash == artifact.content_hash
        else Action.UPDATE
    )


def _classify_keys(root: Path, artifact: Artifact, entry: StateEntry | None) -> Action:
    """Classify a keys artifact against the values on disk at its recorded paths."""
    if not (root / artifact.path).is_file():
        return Action.CREATE if entry is None else Action.MISSING
    if entry is None:
        return Action.INSERT
    if entry.kind is not ArtifactKind.KEYS:
        return Action.CONFLICT
    recorded = entry.key_paths or ()
    disk = ContentHash.of(
        canonical_values(disk_key_values(root, artifact.path, recorded))
    )
    if disk != entry.content_hash:
        return Action.DRIFT
    same = (
        entry.content_hash == artifact.content_hash
        and entry.key_paths == artifact.to_entry().key_paths
    )
    return Action.UNCHANGED if same else Action.UPDATE


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
    if entry.kind is ArtifactKind.KEYS:
        values = disk_key_values(root, entry.path, entry.key_paths or ())
        clean = ContentHash.of(canonical_values(values)) == entry.content_hash
        return (Action.REMOVE if clean else Action.DRIFT), Action.REMOVE
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
            caller has explicitly approved.
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
