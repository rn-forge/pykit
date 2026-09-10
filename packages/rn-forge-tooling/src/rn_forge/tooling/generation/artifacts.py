"""The generation model: artifact kinds, actions, and the plan they describe.

Every artifact is one of three :class:`ArtifactKind` values:

- **managed** — the generator owns the whole file. Hand edits are drift.
- **seeded** — the generator writes the file if it is absent and never looks
  at its contents again. Repos are meant to edit these.
- **block** — the generator owns a fenced region inside a file somebody else
  owns (see :class:`~rn_forge.commons.fs.blocks.ManagedBlock`). The body
  outside the markers is never touched.

This module holds the vocabulary and the shared filesystem helpers.
:mod:`~rn_forge.tooling.generation.plan` decides what a write *would* do;
:mod:`~rn_forge.tooling.generation.apply` makes a batch of writes
all-or-nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

import dacite

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.fs.paths import PathUtils

__all__ = [
    "BLOCKING_ACTIONS",
    "WRITE_ACTIONS",
    "Action",
    "ApplyResult",
    "Artifact",
    "ArtifactKind",
    "Change",
    "Generator",
    "Plan",
    "StateEntry",
]


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

WRITE_ACTIONS = frozenset(
    {Action.CREATE, Action.INSERT, Action.UPDATE, Action.DELETE, Action.REMOVE}
)


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
    intent: Action | None = None
    """What this change *means* to do, when :attr:`action` is a blocking
    classification that hides it. A stale entry whose file was hand-edited
    classifies as :attr:`Action.DRIFT` but still intends to delete the file or
    remove the block; approving the drift executes that intent instead of
    dropping the state entry and leaving the content behind."""

    @property
    def is_blocking(self) -> bool:
        """Whether this change stops the plan from being applied."""
        return self.action in BLOCKING_ACTIONS and not self.approved

    @property
    def effective_action(self) -> Action:
        """The action to execute: :attr:`intent` once approved, else :attr:`action`."""
        if (
            self.approved
            and self.action in BLOCKING_ACTIONS
            and self.intent is not None
        ):
            return self.intent
        return self.action


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


# The three helpers below are shared by `plan` and `apply` and are internal to
# this package: they carry no leading underscore because a module-private name
# used from a sibling module is a contradiction, and they are deliberately not
# re-exported from `generation/__init__.py`.
def read_text(path: Path) -> str:
    """Read *path* without translating its newlines, or ``""`` when it is absent.

    :meth:`pathlib.Path.read_text` opens in universal-newline mode, which
    silently rewrites a CRLF file as LF — so a read/modify/write cycle would
    reformat every line of a file this engine only owns a block of. Reading
    with ``newline=""`` keeps the bytes as they are.
    """
    if not path.is_file():
        return ""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def resolve_within(root: Path, relative: str) -> Path:
    """Resolve a repo-relative artifact path, refusing anything outside *root*.

    Guards the declared escape (``../../.ssh/config``, an absolute path) and
    the symlink escape (a path whose parent resolves outside the repository)
    alike. Called before staging and again before the file is touched, since
    the tree can change between the two.

    Raises:
        AppException: *relative* is absolute or resolves outside *root*.
    """
    if Path(relative).is_absolute():
        raise AppException("Artifact path must be repo-relative, got {!r}", relative)
    return PathUtils.assert_within(root, root / relative)


def block_from_entry(entry: StateEntry) -> ManagedBlock:
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
