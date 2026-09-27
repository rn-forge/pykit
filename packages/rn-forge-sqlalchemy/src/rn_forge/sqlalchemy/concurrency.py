"""Optimistic concurrency over a :class:`~rn_forge.sqlalchemy.VersionMixin` row."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, and_, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rn_forge.sqlalchemy.models import VersionMixin
from rn_forge.web import VersionConflict

__all__ = ["update_versioned"]


async def update_versioned[T: VersionMixin](
    session: AsyncSession, obj: T, **values: Any
) -> T:
    """Update *obj*'s row only if its ``version`` is still the one *obj* holds.

    Issues ``UPDATE … WHERE pk = :pk AND version = :expected`` with
    ``version = expected + 1``, then refreshes *obj*. Does not commit.

    Args:
        session: The session *obj* belongs to.
        obj: A persistent instance of a model using ``VersionMixin``.
        **values: Column values to set.

    Returns:
        *obj*, refreshed.

    Raises:
        VersionConflict: The row exists at a different version (412).
        LookupError: The row no longer exists.
    """
    mapper = inspect(type(obj), raiseerr=True)
    identity = mapper.primary_key_from_instance(obj)
    same_row = and_(
        *(col == value for col, value in zip(mapper.primary_key, identity, strict=True))
    )
    model: Any = type(obj)
    expected = obj.version
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(model)
            .where(same_row, model.version == expected)
            .values(**values, version=expected + 1)
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount == 0:
        if (
            await session.execute(select(1).select_from(model).where(same_row))
        ).first():
            raise VersionConflict(
                "{} {} was modified concurrently: expected version {}",
                type(obj).__name__,
                identity[0] if len(identity) == 1 else identity,
                expected,
                error_code=412,
            )
        raise LookupError(f"{type(obj).__name__} {identity} no longer exists")
    await session.refresh(obj)
    return obj
