from datetime import UTC, datetime, timedelta

import pytest
from assertpy import assert_that
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.sqlalchemy import AuditMixin, Base, keyset, next_page_token
from rn_forge.sqlalchemy.models import UTCDateTime
from rn_forge.web import (
    Cursor,
    InvalidCursor,
    OrderField,
    decode_cursor,
    encode_cursor,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 1, tzinfo=UTC)


class Task(Base):
    __tablename__ = "pagination_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    due: Mapped[datetime] = mapped_column(UTCDateTime)


COLUMNS = {"title": Task.title, "due": Task.due, "id": Task.id}


async def _seed(session):
    session.add_all(
        Task(id=i, title=f"t{i}", due=T0 + timedelta(days=(i * 3) % 5))
        for i in range(1, 8)
    )
    await session.commit()


async def _walk(session, terms, size=2):
    seen: list[int] = []
    cursor = None
    while True:
        stmt = keyset(
            select(Task), columns=COLUMNS, terms=terms, cursor=cursor, id_column=Task.id
        )
        rows = (await session.scalars(stmt.limit(size + 1))).all()
        page = rows[:size]
        seen += [t.id for t in page]
        if len(rows) <= size:
            return seen
        last = page[-1]
        value = getattr(last, terms[0].field) if terms else last.id
        cursor = decode_cursor(next_page_token(value, last.id, terms))


@pytest.mark.parametrize(
    "terms",
    [
        (),
        (OrderField("title"),),
        (OrderField("title", descending=True),),
        (OrderField("due"),),
        (OrderField("due", descending=True),),
    ],
    ids=["default", "title", "title-desc", "due", "due-desc"],
)
@pytest.mark.asyncio
async def test_walking_every_page_visits_each_row_once_in_order(session, terms):
    await _seed(session)
    everything = await session.scalars(
        keyset(
            select(Task), columns=COLUMNS, terms=terms, cursor=None, id_column=Task.id
        )
    )

    assert_that(await _walk(session, terms)).is_equal_to([t.id for t in everything])
    assert_that(await _walk(session, terms)).is_length(7)


@pytest.mark.asyncio
async def test_ties_on_the_sort_column_break_on_the_id(session):
    await _seed(session)

    seen = await _walk(session, (OrderField("due"),), size=1)

    assert_that(seen).is_length(7).does_not_contain_duplicates()


def test_the_token_writes_a_datetime_as_iso_and_the_order_by_canonically():
    token = next_page_token(T0, 5, (OrderField("due", descending=True),))

    assert_that(decode_cursor(token)).is_equal_to(
        Cursor(T0.isoformat(), "5", "due desc")
    )


@pytest.mark.asyncio
async def test_a_token_for_another_order_by_is_invalid_cursor(session):
    cursor = Cursor("1", "1", "title")

    with pytest.raises(InvalidCursor):
        keyset(
            select(Task),
            columns=COLUMNS,
            terms=(),
            cursor=cursor,
            id_column=Task.id,
        )


@pytest.mark.asyncio
async def test_a_token_value_that_does_not_fit_the_column_is_invalid_cursor():
    cursor = Cursor("not-a-date", "1", "due")

    with pytest.raises(InvalidCursor):
        keyset(
            select(Task),
            columns=COLUMNS,
            terms=(OrderField("due"),),
            cursor=cursor,
            id_column=Task.id,
        )


def test_encode_cursor_round_trip_is_what_keyset_reads():
    assert_that(next_page_token("a", 1, ())).is_equal_to(encode_cursor("a", "1"))
