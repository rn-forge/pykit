from datetime import UTC, datetime

import pytest
from assertpy import assert_that
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.sqlalchemy import (
    AuditMixin,
    Base,
    SoftDeleteMixin,
    VersionMixin,
    live,
    soft_delete,
    undelete,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 2, tzinfo=UTC)


class SoftNote(SoftDeleteMixin, VersionMixin, AuditMixin, Base):
    __tablename__ = "soft_delete_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str]


class PlainSoftNote(SoftDeleteMixin, Base):
    __tablename__ = "soft_delete_plain_note"

    id: Mapped[int] = mapped_column(primary_key=True)


def test_delete_time_is_indexed():
    names = {index.name for index in SoftNote.__table__.indexes}
    assert_that(names).contains("ix_soft_delete_note_delete_time")


@pytest.mark.asyncio
async def test_soft_delete_sets_the_columns_and_bumps_the_version(session):
    session.add(SoftNote(id=1, text="a"))
    await session.commit()
    note = await session.get(SoftNote, 1)

    soft_delete(note, actor="alice", now=NOW)
    await session.commit()
    session.expire_all()

    stored = await session.get(SoftNote, 1)
    assert_that(stored.delete_time).is_equal_to(NOW)
    assert_that(stored.updated_by).is_equal_to("alice")
    assert_that(stored.update_time).is_equal_to(NOW)
    assert_that(stored.version).is_equal_to(2)


@pytest.mark.asyncio
async def test_undelete_clears_the_time_and_bumps_the_version(session):
    session.add(SoftNote(id=1, text="a"))
    await session.commit()
    note = await session.get(SoftNote, 1)
    soft_delete(note, actor="alice", now=NOW)
    await session.commit()

    undelete(note, actor="bob", now=NOW)
    await session.commit()
    session.expire_all()

    stored = await session.get(SoftNote, 1)
    assert_that(stored.delete_time).is_none()
    assert_that(stored.updated_by).is_equal_to("bob")
    assert_that(stored.version).is_equal_to(3)


@pytest.mark.asyncio
async def test_a_row_without_audit_or_version_columns_still_soft_deletes(session):
    session.add(PlainSoftNote(id=1))
    await session.commit()
    note = await session.get(PlainSoftNote, 1)

    soft_delete(note, actor="alice", now=NOW)
    await session.commit()
    session.expire_all()

    assert_that((await session.get(PlainSoftNote, 1)).delete_time).is_equal_to(NOW)


@pytest.mark.asyncio
async def test_live_hides_deleted_rows_unless_asked(session):
    session.add_all([SoftNote(id=1, text="a"), SoftNote(id=2, text="b")])
    await session.commit()
    soft_delete(await session.get(SoftNote, 2), actor="alice", now=NOW)
    await session.commit()

    only_live = await session.scalars(live(select(SoftNote), SoftNote))
    everything = await session.scalars(
        live(select(SoftNote), SoftNote, show_deleted=True)
    )

    assert_that([n.id for n in only_live]).is_equal_to([1])
    assert_that(sorted(n.id for n in everything)).is_equal_to([1, 2])
