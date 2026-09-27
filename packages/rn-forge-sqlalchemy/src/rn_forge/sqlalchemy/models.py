"""Declarative base, UTC timestamps and the audit and version mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import DateTime, Dialect, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

__all__ = [
    "NAMING_CONVENTION",
    "AuditMixin",
    "Base",
    "UTCDateTime",
    "VersionMixin",
]

NAMING_CONVENTION: Final = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Constraint names Alembic can address in a migration."""


class Base(DeclarativeBase):
    """Declarative base whose metadata carries :data:`NAMING_CONVENTION`."""

    metadata = MetaData(naming_convention=dict(NAMING_CONVENTION))


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware ``datetime`` stored as UTC on every dialect.

    Writing a naive value raises ``ValueError``. Reading returns an aware UTC
    value, including from SQLite, which stores no zone.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @property
    def python_type(self) -> type[datetime]:
        return datetime

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class AuditMixin:
    """AIP-148 timestamps and the actors behind them.

    ``create_time`` and ``update_time`` default to the current UTC time, and
    ``update_time`` is refreshed on every ORM or Core update. ``created_by`` and
    ``updated_by`` are set by the caller; :func:`rn_forge.sqlalchemy.upsert` sets
    all four.
    """

    create_time: Mapped[datetime] = mapped_column(
        UTCDateTime, default=_now, nullable=False
    )
    update_time: Mapped[datetime] = mapped_column(
        UTCDateTime, default=_now, onupdate=_now, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)
    updated_by: Mapped[str | None] = mapped_column(String(255), default=None)


class VersionMixin:
    """A ``version`` counter, starting at 1, for :func:`update_versioned`."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
