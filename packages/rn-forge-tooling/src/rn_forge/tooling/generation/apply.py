"""Transactional application: stage everything, back up once, then swap it in.

Changes are grouped by *destination*, not by artifact: the block edits for one
file are composed against a single evolving buffer, and every destination is
backed up and written exactly once. Anything raised during the writes — the
caller's ``verify`` callback included — restores the working tree and the
state file before propagating.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.logging import AppLogger

from rn_forge.tooling.generation.artifacts import (
    Action,
    ApplyResult,
    ArtifactKind,
    Change,
    Plan,
    StateEntry,
    block_from_entry,
    read_text,
    resolve_within,
)
from rn_forge.tooling.state import StateStore

__all__ = ["apply"]

_LOGGER = AppLogger.get_logger(__name__)


def _compose(
    root: Path, writes: Sequence[Change], previous: Mapping[str, StateEntry]
) -> dict[str, str | None]:
    """The final text of every destination this plan touches, keyed by path.

    Changes are grouped by destination rather than by artifact, and the block
    edits for one file are composed against a single evolving buffer. Rendering
    each block against the original on-disk text would leave only the last
    block's edit, and writing each block separately would back the same file up
    more than once — the second backup capturing content the first write had
    already changed, which is what rollback restores.

    Returns:
        Destination path to its new text, or ``None`` when it is to be deleted.
        Insertion order is apply order.
    """
    grouped: dict[str, list[Change]] = {}
    for change in writes:
        grouped.setdefault(change.path, []).append(change)

    rendered: dict[str, str | None] = {}
    for path, changes in grouped.items():
        blocks = [change for change in changes if change.kind is ArtifactKind.BLOCK]
        whole = [change for change in changes if change.kind is not ArtifactKind.BLOCK]
        if whole and blocks:
            raise AppException(
                "{}: claimed both as a whole file and as a managed block; "
                "one generator must own it",
                path,
            )
        if whole:
            rendered[path] = _render_whole(whole[0])
            continue
        buffer = read_text(root / path)
        for change in blocks:
            buffer = _render_block(buffer, change, previous)
        rendered[path] = buffer
    return rendered


def _render_whole(change: Change) -> str | None:
    """The new text of a whole-file change, or ``None`` when it is deleted."""
    if change.effective_action is Action.DELETE:
        return None
    artifact = change.artifact
    if artifact is None:
        raise AppException(
            "{}: no artifact to write for {}", change.path, change.action
        )
    return artifact.content


def _render_block(
    buffer: str, change: Change, previous: Mapping[str, StateEntry]
) -> str:
    """*buffer* with this block change applied, leaving every other byte alone."""
    if change.effective_action is Action.REMOVE:
        return block_from_entry(previous[change.key]).remove(buffer)
    artifact = change.artifact
    if artifact is None or artifact.block is None:
        raise AppException("{}: no block artifact to write", change.key)
    return artifact.block.render(buffer, artifact.content)


def apply(
    root: str | Path,
    planned: Plan,
    store: StateStore[StateEntry],
    *,
    staging_dir: str | Path,
    backup_dir: str | Path,
    entries: Mapping[str, StateEntry] | None = None,
    verify: Callable[[], None] | None = None,
    dry_run: bool = False,
) -> ApplyResult:
    """Apply *planned* transactionally: stage everything, then swap it in.

    Every new file is rendered into *staging_dir* and every file about to be
    overwritten or deleted is copied under a timestamped directory in
    *backup_dir* before the first replacement happens. If any write, or the
    *verify* callback, raises, the working tree and the state file are restored
    to what they were.

    Args:
        root: The repository root.
        planned: The plan to apply. Checked first; an unapproved blocking
            change aborts before anything is written.
        store: Where the applied state is recorded. Written last, and excluded
            from the artifacts it records — a state file that hashed itself
            could never be consistent.
        staging_dir: Directory rendered content is staged into. Derived data;
            callers gitignore it.
        backup_dir: Directory backups are written under, as
            ``<backup_dir>/<UTC timestamp>/<repo-relative path>``.
        entries: The previous state, used to recover block markers for
            :attr:`Action.REMOVE`. Defaults to ``store.load()``.
        verify: Called after every write and before the state file is written.
            Raise from it to roll the whole apply back.
        dry_run: Classify and report, write nothing.

    Raises:
        AppException: The plan has unapproved blocking changes, an artifact
            path escapes *root*, or a write failed (after the working tree has
            been restored).
        BaseException: An interruption (:exc:`KeyboardInterrupt`,
            :exc:`SystemExit`) during the apply is re-raised unchanged, once
            the working tree and the state file have been restored. Converting
            it to an :class:`AppException` would let a caller catch it and
            carry on as though the run had merely failed.
    """
    root = Path(root)
    planned.check()
    writes = planned.writes

    if dry_run:
        return ApplyResult(changes=planned.changes, dry_run=True)

    previous = dict(entries if entries is not None else store.load())
    staging = Path(staging_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backups = Path(backup_dir) / stamp

    rendered = _compose(root, writes, previous)

    staged: dict[str, Path] = {}
    for path, text in rendered.items():
        if text is None:
            continue
        staged_path = staging / path
        PathUtils.assert_within(staging, staged_path)
        PathUtils.atomic_write(text, staged_path)
        staged[path] = staged_path

    created: list[Path] = []
    backed_up: list[tuple[Path, Path]] = []
    state_backup = _backup(root, store.path, backups)

    try:
        for path, text in rendered.items():
            target = resolve_within(root, path)
            if target.is_file():
                copied = _backup(root, target, backups)
                if copied is not None:
                    backed_up.append((target, copied))
            else:
                created.append(target)
            if text is None:
                target.unlink(missing_ok=True)
                continue
            PathUtils.atomic_write(read_text(staged[path]), target)
        if verify is not None:
            verify()
        store.replace_all(_next_entries(planned))
    except BaseException as exc:
        _rollback(created, backed_up, store.path, state_backup)
        if isinstance(exc, Exception):
            raise AppException("Apply failed and was rolled back: {}", exc) from exc
        raise

    _LOGGER.verbose("generation.apply: applied {} change(s)", len(writes))
    return ApplyResult(changes=planned.changes, backup_dir=backups)


def _next_entries(planned: Plan) -> dict[str, StateEntry]:
    """The state entries an applied plan records."""
    return {
        change.key: change.artifact.to_entry()
        for change in planned.changes
        if change.artifact is not None
        and change.action not in (Action.FORGET, Action.DELETE, Action.REMOVE)
    }


def _backup(root: Path, path: Path, backups: Path) -> Path | None:
    """Copy *path* under *backups*, preserving its position relative to *root*."""
    return PathUtils.backup(path, backups, relative_to=root)


def _rollback(
    created: Sequence[Path],
    backed_up: Sequence[tuple[Path, Path]],
    state_path: Path,
    state_backup: Path | None,
) -> None:
    """Restore every backed-up file and remove everything this apply created."""
    for target, copied in backed_up:
        shutil.copy2(copied, target)
    for target in created:
        target.unlink(missing_ok=True)
    if state_backup is not None:
        shutil.copy2(state_backup, state_path)
    else:
        state_path.unlink(missing_ok=True)
