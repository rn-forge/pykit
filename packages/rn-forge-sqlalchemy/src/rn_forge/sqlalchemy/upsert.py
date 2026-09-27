"""Bulk create-or-update by natural key, on PostgreSQL and SQLite."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Table, select, tuple_
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from rn_forge.sqlalchemy.models import AuditMixin, Base

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

    The existing rows are read first, so the counts are exact. Created and
    updated rows are then written with one
    ``INSERT … ON CONFLICT (key) DO UPDATE``; ``create_time`` and ``created_by``
    are set on insert only, ``update_time`` and ``updated_by`` on both. Never
    commits: the caller's transaction decides, and rolling back after the call is
    a dry run. *key* must be backed by a unique constraint.

    Args:
        session: An ``AsyncSession`` on PostgreSQL or SQLite.
        model: A model using :class:`~rn_forge.sqlalchemy.AuditMixin`.
        rows: One mapping per row, holding every column in *key* and *fields*.
        key: The natural-key columns.
        fields: The non-key columns to write.
        actor: Stamped into ``created_by`` and ``updated_by``.

    Raises:
        ValueError: A row lacks a column, or two rows share a key.
        TypeError: *model* does not use ``AuditMixin``.
        NotImplementedError: The session's dialect is not PostgreSQL or SQLite.
    """
    if not issubclass(model, AuditMixin):
        raise TypeError(f"{model.__name__} must use AuditMixin")
    columns = [*key, *fields]
    keyed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        if missing := [c for c in columns if c not in row]:
            raise ValueError(f"row lacks columns {missing}")
        identity = tuple(row[k] for k in key)
        if identity in keyed:
            raise ValueError(f"duplicate key {identity}")
        keyed[identity] = row
    dialect = session.get_bind().dialect.name
    if dialect not in ("postgresql", "sqlite"):
        raise NotImplementedError(f"upsert does not support {dialect}")

    table: Table = model.__table__  # pyright: ignore[reportAssignmentType]
    existing = await _existing(session, table, key, fields, list(keyed))
    to_write: list[dict[str, Any]] = []
    created = updated = 0
    now = datetime.now(UTC)
    for identity, row in keyed.items():
        current = existing.get(identity)
        if current is not None and all(row[f] == current[f] for f in fields):
            continue
        if current is None:
            created += 1
        else:
            updated += 1
        to_write.append(
            {c: row[c] for c in columns}
            | {
                "create_time": now,
                "created_by": actor,
                "update_time": now,
                "updated_by": actor,
            }
        )
    if to_write:
        insert = (postgresql if dialect == "postgresql" else sqlite).insert(table)
        statement = insert.on_conflict_do_update(
            index_elements=list(key),
            set_={
                name: insert.excluded[name]
                for name in (*fields, "update_time", "updated_by")
            },
        )
        await session.execute(statement, to_write)
    return UpsertCounts(created, updated, len(keyed) - created - updated)


async def _existing(
    session: AsyncSession,
    table: Table,
    key: Sequence[str],
    fields: Sequence[str],
    identities: list[tuple[Any, ...]],
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    key_columns = [table.c[k] for k in key]
    found: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for chunk in _chunks(identities, _MAX_PARAMETERS // len(key)):
        match = (
            key_columns[0].in_([i[0] for i in chunk])
            if len(key) == 1
            else tuple_(*key_columns).in_(chunk)
        )
        result = await session.execute(
            select(*key_columns, *(table.c[f] for f in fields)).where(match)
        )
        for record in result.mappings():
            found[tuple(record[k] for k in key)] = dict(record)
    return found


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
