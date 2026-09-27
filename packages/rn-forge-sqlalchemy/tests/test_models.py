from datetime import UTC, datetime, timedelta, timezone

import pytest
from assertpy import assert_that
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.sqlalchemy import NAMING_CONVENTION, AuditMixin, Base, UTCDateTime

pytestmark = pytest.mark.unit


class Note(AuditMixin, Base):
    __tablename__ = "models_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(unique=True)


def test_the_metadata_carries_the_naming_convention():
    assert_that(Base.metadata.naming_convention).is_equal_to(dict(NAMING_CONVENTION))
    names = {c.name for c in Note.__table__.constraints}
    assert_that(names).contains("pk_models_note", "uq_models_note_body")


@pytest.mark.asyncio
async def test_a_naive_datetime_is_rejected(session):
    session.add(Note(body="a", create_time=datetime(2026, 1, 1)))
    with pytest.raises(Exception, match="timezone-aware"):
        await session.flush()


@pytest.mark.asyncio
async def test_a_timestamp_reads_back_as_aware_utc_and_serializes_with_z(session):
    zone = timezone(timedelta(hours=5))
    session.add(Note(body="a", create_time=datetime(2026, 1, 1, 5, 0, tzinfo=zone)))
    await session.commit()
    session.expire_all()

    note = (await session.scalars(select(Note))).one()

    assert_that(note.create_time).is_equal_to(datetime(2026, 1, 1, tzinfo=UTC))
    assert_that(note.create_time.utcoffset()).is_equal_to(timedelta(0))
    dumped = TypeAdapter(datetime).dump_python(note.create_time, mode="json")
    assert_that(dumped).is_equal_to("2026-01-01T00:00:00Z")


@pytest.mark.asyncio
async def test_audit_defaults_and_update_time_refresh(session):
    session.add(Note(body="a"))
    await session.commit()
    note = (await session.scalars(select(Note))).one()
    created = note.update_time
    assert_that(note.create_time.tzinfo).is_equal_to(UTC)
    assert_that(note.created_by).is_none()

    note.body = "b"
    await session.commit()
    await session.refresh(note)

    assert_that(note.update_time).is_greater_than(created)
    assert_that(note.create_time).is_less_than_or_equal_to(created)
