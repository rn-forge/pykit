"""Artifact, action, plan, and result models for file generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import tomlkit
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.fs.documents import ConfigFormat, DocumentError, DocumentUtils
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.lang.collections import (
    _split_key_path,  # pyright: ignore[reportPrivateUsage]
)
from rn_forge.commons.lang.dataclasses import DataclassMixin

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
    KEYS = "keys"
    """The generator owns named key paths inside a JSON or TOML document another program also writes."""


class Action(StrEnum):
    """What applying an artifact would do."""

    CREATE = "create"
    """The file does not exist and will be written."""
    INSERT = "insert"
    """The block or owned keys are absent and will be inserted; the rest of the file is untouched."""
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
    """No longer rendered; the block or owned keys will be removed, the rest of the file untouched."""
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
    supposed to edit would turn every legitimate edit into drift. A keys entry
    records :attr:`key_paths`, the sorted dotted paths the generator owned, so a
    later render that drops one can remove it.

    """

    path: str
    kind: ArtifactKind
    content_hash: str | None = None
    begin_marker: str | None = None
    end_marker: str | None = None
    key_paths: tuple[str, ...] | None = None


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
        keys: Dotted key path to value, required for (and only valid on) a
            :attr:`ArtifactKind.KEYS` artifact. A value is owned whole.
    """

    path: str
    kind: ArtifactKind
    content: str
    block: ManagedBlock | None = None
    keys: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if (self.kind is ArtifactKind.BLOCK) != (self.block is not None):
            raise ValueError(
                f"{self.path}: a block artifact needs a ManagedBlock, "
                "and only a block artifact may have one"
            )
        if (self.kind is ArtifactKind.KEYS) != bool(self.keys):
            raise ValueError(
                f"{self.path}: a keys artifact needs non-empty keys, "
                "and only a keys artifact may have them"
            )
        if self.kind is ArtifactKind.KEYS:
            if self.content:
                raise ValueError(f"{self.path}: a keys artifact has no content")
            try:
                fmt = ConfigFormat.of(Path(self.path))
            except DocumentError:
                fmt = None
            if fmt not in (ConfigFormat.JSON, ConfigFormat.TOML):
                raise ValueError(f"{self.path}: keys need a JSON or TOML file")

    @property
    def key(self) -> str:
        """The artifact's state key: its path, plus the block name for a block."""
        return f"{self.path}#{self.block.name}" if self.block else self.path

    @property
    def content_hash(self) -> str:
        """SHA-256 of :attr:`content` — for a block, of the body as written to disk.

        A block body is re-terminated when rendered (``"value"`` is written as
        ``"value\\n"``), so the hash is taken of what :meth:`ManagedBlock.extract`
        will read back; otherwise an untouched block would plan as drift.
        """
        if self.keys is not None:
            return ContentHash.of(canonical_values(self.keys))
        if self.block is None:
            return ContentHash.of(self.content)
        return ContentHash.of(
            self.block.extract(self.block.render("", self.content)) or ""
        )

    def to_entry(self) -> StateEntry:
        """The state entry recording this artifact as applied."""
        if self.kind is ArtifactKind.SEEDED:
            return StateEntry(path=self.path, kind=self.kind)
        if self.keys is not None:
            return StateEntry(
                path=self.path,
                kind=self.kind,
                content_hash=self.content_hash,
                key_paths=tuple(sorted(self.keys)),
            )
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
        """Repo-relative write paths, once each in plan order; empty for dry runs."""
        if self.dry_run:
            return ()
        return tuple(dict.fromkeys(change.path for change in Plan(self.changes).writes))


# Internal helpers shared by the planning and application modules.
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


def canonical_values(values: Mapping[str, Any]) -> str:
    """The canonical JSON form of a ``{key path: value}`` mapping, for hashing."""
    return json.dumps(
        values, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def disk_key_values(
    root: Path, relative: str, key_paths: Sequence[str]
) -> dict[str, Any]:
    """The values *relative* holds at *key_paths*; an absent path is left out."""
    data = DocumentUtils.read(root / relative)
    found: dict[str, Any] = {}
    for key_path in key_paths:
        current: Any = data
        for segment in _split_key_path(key_path):
            if not isinstance(current, Mapping) or segment not in current:
                break
            current = cast(Any, current[segment])
        else:
            found[key_path] = current
    return found


def render_keys(root: Path, change: Change, previous: Mapping[str, StateEntry]) -> str:
    """The text of a keys file with *change* applied, leaving other keys alone.

    Sets every owned path unless the change removes them, and deletes the
    paths a previous keys entry recorded that the artifact no longer owns.

    Raises:
        AppException: An owned path runs through a non-table on disk.
    """
    path = change.path
    target = root / path
    fmt = ConfigFormat.of(Path(path))
    if target.is_file():
        document: Any = DocumentUtils.read_document(target)
    else:
        document = tomlkit.document() if fmt is ConfigFormat.TOML else {}
    entry = previous.get(change.key)
    recorded = (
        entry.key_paths or ()
        if entry is not None and entry.kind is ArtifactKind.KEYS
        else ()
    )
    artifact = change.artifact
    owned: Mapping[str, Any] = artifact.keys or {} if artifact is not None else {}
    removing = change.effective_action is Action.REMOVE
    for key_path in recorded:
        if removing or key_path not in owned:
            _delete_key(document, key_path)
    if not removing:
        for key_path, value in owned.items():
            _set_key(document, path, key_path, value, fmt)
    return DocumentUtils.serialize_document(path, document)


def _set_key(
    document: Any, path: str, key_path: str, value: Any, fmt: ConfigFormat
) -> None:
    *parents, last = _split_key_path(key_path)
    current: Any = document
    for segment in parents:
        if segment not in current:
            current[segment] = tomlkit.table() if fmt is ConfigFormat.TOML else {}
        current = current[segment]
        if not isinstance(current, MutableMapping):
            raise AppException(
                "{}: key path {!r} runs through a non-table", path, key_path
            )
        current = cast(MutableMapping[str, Any], current)
    current[last] = value


def _delete_key(document: Any, key_path: str) -> None:
    *parents, last = _split_key_path(key_path)
    chain: list[MutableMapping[str, Any]] = [document]
    for segment in parents:
        node = chain[-1]
        if segment not in node or not isinstance(node[segment], MutableMapping):
            return
        chain.append(cast(MutableMapping[str, Any], node[segment]))
    if last not in chain[-1]:
        return
    del chain[-1][last]
    names = [*parents]
    while names and not chain[-1]:
        chain.pop()
        del chain[-1][names.pop()]
