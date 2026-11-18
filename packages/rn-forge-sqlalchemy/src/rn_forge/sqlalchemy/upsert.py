"""Bulk create-or-update by natural key, on PostgreSQL and SQLite."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import batched
from typing import Any

from rn_forge.sqlalchemy.models import AuditMixin, Base
from sqlalchemy import Table, select, tuple_
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["UpsertCounts", "upsert"]

# SQLite's bound-parameter limit is 999 before 3.32.
_MAX_PARAMETERS = 900


@dataclass(frozen=True)
class UpsertCounts:
    """How many input rows :func:`upsert` created, updated and left unchanged."""

    created: int
    updated: int
    skipped: int


async def upsert(
    session: AsyncSession,
    model: type[Base],
    rows: Sequence[Mapping[str, Any]],
    *,
    key: Sequence[str],
    fields: Sequence[str],
    actor: str,
) -> UpsertCounts:
    """Create the rows whose *key* is absent and update those whose *fields* differ.

    The existing rows are read first, and the counts describe that snapshot. A
    writer that commits between the read and the write can make them wrong, so
    serialize writers when exact counts matter. Only new and changed rows are
    written, with one ``INSERT … ON CONFLICT (key) DO UPDATE``; ``create_time``
    and ``created_by`` are set on insert only, ``update_time`` and ``updated_by``
    on both. Never commits: the caller's transaction decides, and rolling back
    after the call is a dry run. *key* must be backed by a unique constraint.

    Args:
        session: An ``AsyncSession`` on PostgreSQL or SQLite.
        model: A model using :class:`~rn_forge.sqlalchemy.AuditMixin`.
        rows: One mapping per row, holding every column in *key* and *fields*.
        key: The natural-key columns.
        fields: The non-key columns to write.
        actor: Stamped into ``created_by`` and ``updated_by``.

    Raises:
        ValueError: *key* is empty, a row lacks a column, or two rows share a key.
        TypeError: *model* does not use ``AuditMixin``.
        NotImplementedError: The session's dialect is not PostgreSQL or SQLite.
    """
    if not issubclass(model, AuditMixin):
        raise TypeError(f"{model.__name__} must use AuditMixin")
    if not key:
        raise ValueError("key must not be empty")
    columns = [*key, *fields]
    keyed = _keyed(rows, key, columns)
    dialect = session.get_bind().dialect.name
    if dialect not in ("postgresql", "sqlite"):
        raise NotImplementedError(f"upsert does not support {dialect}")
    del keyed

    table: Table = model.__table__  # pyright: ignore[reportAssignmentType]
    total = len(rows)
    to_write: list[dict[str, Any]] = []
    created = updated = 0
    now = datetime.now(UTC)
    stamps = {
        "create_time": now,
        "created_by": actor,
        "update_time": now,
        "updated_by": actor,
    }
    for chunk in batched(rows, _MAX_PARAMETERS // len(key)):
        identities = [tuple(row[k] for k in key) for row in chunk]
        existing = await _existing(session, table, key, fields, identities)
        changes, new, changed = _changes(chunk, identities, existing, columns, fields)
        to_write.extend(changes)
        created += new
        updated += changed
        del existing
    if to_write:
        insert = (
            (postgresql if dialect == "postgresql" else sqlite)
            .insert(table)
            .values(stamps)
        )
        statement = insert.on_conflict_do_update(
            index_elements=list(key),
            set_={
                name: insert.excluded[name]
                for name in (*fields, "update_time", "updated_by")
            },
        )
        await session.execute(statement, to_write)
    return UpsertCounts(created, updated, total - created - updated)


def _keyed(
    rows: Sequence[Mapping[str, Any]], key: Sequence[str], columns: Sequence[str]
) -> set[tuple[Any, ...]]:
    keyed: set[tuple[Any, ...]] = set()
    for row in rows:
        if missing := [c for c in columns if c not in row]:
            raise ValueError(f"row lacks columns {missing}")
        identity = tuple(row[k] for k in key)
        if identity in keyed:
            raise ValueError(f"duplicate key {identity}")
        keyed.add(identity)
    return keyed


def _changes(
    rows: Sequence[Mapping[str, Any]],
    identities: Sequence[tuple[Any, ...]],
    existing: Mapping[tuple[Any, ...], Mapping[str, Any]],
    columns: Sequence[str],
    fields: Sequence[str],
) -> tuple[list[dict[str, Any]], int, int]:
    """The rows to write, with how many of them are creations and updates."""
    to_write: list[dict[str, Any]] = []
    created = updated = 0
    for identity, row in zip(identities, rows, strict=True):
        current = existing.get(identity)
        if current is not None and all(row[f] == current[f] for f in fields):
            continue
        if current is None:
            created += 1
        else:
            updated += 1
        to_write.append({c: row[c] for c in columns})
    return to_write, created, updated


async def _existing(
    session: AsyncSession,
    table: Table,
    key: Sequence[str],
    fields: Sequence[str],
    identities: list[tuple[Any, ...]],
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    key_columns = [table.c[k] for k in key]
    found: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    match = (
        key_columns[0].in_([i[0] for i in identities])
        if len(key) == 1
        else tuple_(*key_columns).in_(identities)
    )
    result = await session.execute(
        select(*key_columns, *(table.c[f] for f in fields)).where(match)
    )
    for record in result.mappings():
        found[tuple(record[k] for k in key)] = dict(record)
    return found
