"""The generation engine: artifact kinds, action classification, transactional apply.

This is the runtime-neutral half of "generate a repo's standard files". It
knows how to decide *what* a write would do to a working tree and how to make
a batch of writes all-or-nothing. It does not know what a repo standard is,
where config lives, or what a template renders to — a generator supplies the
artifacts, and the caller supplies the state store, the staging and backup
directories and any force approvals.

Nothing here imports Typer or a CLI framework: a generator must be callable as
plain Python (``generator.generate(context)``) so that command-line parsing
never becomes its API.

The model
~~~~~~~~~

Every artifact is one of three :class:`ArtifactKind` values:

- **managed** — the generator owns the whole file. Hand edits are drift.
- **seeded** — the generator writes the file if it is absent and never looks
  at its contents again. Repos are meant to edit these.
- **block** — the generator owns a fenced region inside a file somebody else
  owns (see :class:`~rn_forge.commons.blocks.ManagedBlock`). The body outside
  the markers is never touched.

:func:`classify` maps (rendered content, disk content, last-applied state) to
an :class:`Action`. :class:`Plan` collects those; actions that mean "the
working tree disagrees with what I last wrote" (:attr:`Action.DRIFT`,
:attr:`Action.CONFLICT`, :attr:`Action.MISSING`) are *blocking*: they abort
the whole plan before anything is written unless the caller has explicitly
approved that path.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

import dacite

from rn_forge.commons.blocks import ManagedBlock
from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.utils import ContentHash, PathUtils

from rn_forge.tooling.state import StateStore

__all__ = [
    "Action",
    "ApplyResult",
    "Artifact",
    "ArtifactKind",
    "Change",
    "Generator",
    "Plan",
    "StateEntry",
    "apply",
    "classify",
    "plan",
]

_LOGGER = AppLogger.get_logger(__name__)


class ArtifactKind(StrEnum):
    """Who owns the bytes at an artifact's path."""

    MANAGED = "managed"
    """The generator owns the whole file."""
    SEEDED = "seeded"
    """Written once if absent, then owned by the repository."""
    BLOCK = "block"
    """The generator owns one fenced block inside a repository-owned file."""


class Action(StrEnum):
    """What applying an artifact would do."""

    CREATE = "create"
    """The file does not exist and will be written."""
    INSERT = "insert"
    """The block is absent and will be inserted; the file body is untouched."""
    UPDATE = "update"
    """The rendered content differs from what was last applied."""
    UNCHANGED = "unchanged"
    """Disk, last-applied and freshly-rendered content all agree."""
    SKIP = "skip"
    """A seeded artifact that already exists; its content is never inspected."""
    DRIFT = "drift"
    """Disk differs from what was last applied — a hand edit. Blocking."""
    CONFLICT = "conflict"
    """Something exists at a managed path that this generator never wrote. Blocking."""
    MISSING = "missing"
    """Recorded as applied, but gone from disk. Blocking."""
    DELETE = "delete"
    """No longer rendered; the file will be backed up and removed."""
    REMOVE = "remove"
    """No longer rendered; the block will be removed, the file body untouched."""
    FORGET = "forget"
    """No longer rendered and nothing to remove; only the state entry goes."""


BLOCKING_ACTIONS = frozenset({Action.DRIFT, Action.CONFLICT, Action.MISSING})
"""Actions that abort a plan unless the caller explicitly approved the path."""

WRITE_ACTIONS = frozenset(
    {Action.CREATE, Action.INSERT, Action.UPDATE, Action.DELETE, Action.REMOVE}
)
"""Actions that touch the working tree."""


@dataclass(frozen=True, slots=True)
class StateEntry(DataclassMixin):
    """One artifact as it was last applied, as recorded in the state file.

    A seeded entry records presence only: hashing content the repository is
    supposed to edit would turn every legitimate edit into drift.
    """

    #: The state file is committed, reviewed and hand-editable, so it is
    #: validated strictly on load: a truncated or mistyped entry must surface
    #: here rather than as an unrelated error in the middle of an apply.
    __dacite_config__: ClassVar[dacite.Config] = dacite.Config(
        check_types=True, cast=[ArtifactKind, tuple, set]
    )

    path: str
    kind: ArtifactKind
    content_hash: str | None = None
    begin_marker: str | None = None
    end_marker: str | None = None


@dataclass(frozen=True, slots=True)
class Artifact:
    """One rendered artifact, ready to classify.

    Args:
        path: Repo-relative path of the file this artifact lives in.
        kind: See :class:`ArtifactKind`.
        content: The rendered content. For a block artifact this is the block
            *body* — what goes between the markers — not the whole file.
        block: The fenced block, required for (and only valid on) a
            :attr:`ArtifactKind.BLOCK` artifact.
    """

    path: str
    kind: ArtifactKind
    content: str
    block: ManagedBlock | None = None

    def __post_init__(self) -> None:
        if (self.kind is ArtifactKind.BLOCK) != (self.block is not None):
            raise ValueError(
                f"{self.path}: a block artifact needs a ManagedBlock, "
                "and only a block artifact may have one"
            )

    @property
    def key(self) -> str:
        """The artifact's state key: its path, plus the block name for a block."""
        return f"{self.path}#{self.block.name}" if self.block else self.path

    @property
    def content_hash(self) -> str:
        """SHA-256 of :attr:`content`."""
        return ContentHash.of(self.content)

    def to_entry(self) -> StateEntry:
        """The state entry recording this artifact as applied."""
        if self.kind is ArtifactKind.SEEDED:
            return StateEntry(path=self.path, kind=self.kind)
        if self.block is not None:
            return StateEntry(
                path=self.path,
                kind=self.kind,
                content_hash=self.content_hash,
                begin_marker=self.block.begin,
                end_marker=self.block.end,
            )
        return StateEntry(
            path=self.path, kind=self.kind, content_hash=self.content_hash
        )


@runtime_checkable
class Generator(Protocol):
    """A source of artifacts, callable as plain Python.

    Implementations must not import a CLI framework and must not write to the
    working tree — rendering is pure, and :func:`apply` owns every write.
    """

    @property
    def name(self) -> str:
        """Stable identifier for this generator, used in reporting."""
        ...

    def generate(self, context: Mapping[str, object]) -> Sequence[Artifact]:
        """Render every artifact this generator owns for *context*."""
        ...


@dataclass(frozen=True, slots=True)
class Change:
    """One planned change: an artifact (or a stale state entry) and its action."""

    key: str
    path: str
    kind: ArtifactKind
    action: Action
    artifact: Artifact | None = None
    approved: bool = False

    @property
    def is_blocking(self) -> bool:
        """Whether this change stops the plan from being applied."""
        return self.action in BLOCKING_ACTIONS and not self.approved


@dataclass(frozen=True, slots=True)
class Plan:
    """The classified result of rendering every artifact, before any write."""

    changes: tuple[Change, ...] = ()

    @property
    def blocking(self) -> tuple[Change, ...]:
        """Changes that must be approved (forced) before this plan can apply."""
        return tuple(change for change in self.changes if change.is_blocking)

    @property
    def writes(self) -> tuple[Change, ...]:
        """Changes that would touch the working tree, in apply order."""
        return tuple(
            change
            for change in self.changes
            if change.action in WRITE_ACTIONS
            or (change.approved and change.action in BLOCKING_ACTIONS)
        )

    def check(self) -> None:
        """Raise if this plan cannot be applied.

        Raises:
            AppException: One or more changes are blocking and unapproved.
        """
        blocking = self.blocking
        if blocking:
            raise AppException(
                "Refusing to apply: {} unapproved change(s): {}",
                len(blocking),
                ", ".join(f"{c.path} ({c.action})" for c in blocking),
            )


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """What :func:`apply` did."""

    changes: tuple[Change, ...] = ()
    backup_dir: Path | None = None
    dry_run: bool = False

    @property
    def written(self) -> tuple[str, ...]:
        """Repo-relative paths whose bytes changed."""
        return tuple(change.path for change in self.changes)


def _disk_content(root: Path, artifact: Artifact) -> str | None:
    """The artifact's current content on disk (block body for a block), or ``None``."""
    path = root / artifact.path
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
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


def _stale_action(root: Path, entry: StateEntry) -> Action:
    """Classify a state entry that the current render no longer produces."""
    path = root / entry.path
    if entry.kind is ArtifactKind.SEEDED:
        return Action.FORGET
    if not path.is_file():
        return Action.FORGET
    if entry.kind is ArtifactKind.BLOCK:
        if entry.begin_marker is None or entry.end_marker is None:
            return Action.FORGET
        block = _block_from_entry(entry)
        body = block.extract(path.read_text(encoding="utf-8"))
        if body is None:
            return Action.FORGET
        return (
            Action.REMOVE
            if ContentHash.of(body) == entry.content_hash
            else Action.DRIFT
        )
    disk_hash = ContentHash.of_file(path)
    return Action.DELETE if disk_hash == entry.content_hash else Action.DRIFT


def _block_from_entry(entry: StateEntry) -> ManagedBlock:
    """Reconstruct the block a state entry recorded, from its exact markers."""
    begin = entry.begin_marker or ""
    indent = begin[: len(begin) - len(begin.lstrip())]
    stripped = begin.strip()
    if stripped.startswith("<!--"):
        name = stripped.removeprefix("<!--").strip().removeprefix("BEGIN").strip()
        name = name.removesuffix("-->").strip()
        return ManagedBlock(name, comment="<!--", indent=indent)
    name = stripped.removeprefix("#").strip().removeprefix("BEGIN").strip()
    return ManagedBlock(name, indent=indent)


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
        action = _stale_action(root, entry)
        changes.append(
            Change(
                key=key,
                path=entry.path,
                kind=entry.kind,
                action=action,
                approved=key in approved or entry.path in approved,
            )
        )

    return Plan(tuple(changes))


def _render_file(
    root: Path, change: Change, previous: Mapping[str, StateEntry]
) -> str | None:
    """The full new text of *change*'s file, or ``None`` when the file goes away."""
    path = root / change.path

    if change.action is Action.DELETE:
        return None
    if change.action is Action.REMOVE:
        block = _block_from_entry(previous[change.key])
        return block.remove(path.read_text(encoding="utf-8"))

    artifact = change.artifact
    if artifact is None:
        return None
    if artifact.block is None:
        return artifact.content
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    return artifact.block.render(existing, artifact.content)


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
        AppException: The plan has unapproved blocking changes, or a write
            failed (after the working tree has been restored).
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

    staged: dict[str, Path] = {}
    for change in writes:
        text = _render_file(root, change, previous)
        if text is None:
            continue
        staged_path = staging / change.path
        PathUtils.atomic_write(text, staged_path)
        staged[change.path] = staged_path

    created: list[Path] = []
    backed_up: list[tuple[Path, Path]] = []
    state_backup = _backup(root, store.path, backups)

    try:
        for change in writes:
            target = root / change.path
            if target.is_file():
                copied = _backup(root, target, backups)
                if copied is not None:
                    backed_up.append((target, copied))
            else:
                created.append(target)
            if change.action is Action.DELETE:
                target.unlink(missing_ok=True)
                continue
            source = staged.get(change.path)
            if source is None:
                continue
            PathUtils.atomic_write(source.read_text(encoding="utf-8"), target)
        if verify is not None:
            verify()
        store.replace_all(_next_entries(planned))
    except Exception as exc:
        _rollback(created, backed_up, store.path, state_backup)
        raise AppException("Apply failed and was rolled back: {}", exc) from exc

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
