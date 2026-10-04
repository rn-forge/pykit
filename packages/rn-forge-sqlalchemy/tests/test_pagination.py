from datetime import UTC, datetime, timedelta
from itertools import permutations, product

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


class Person(Base):
    __tablename__ = "pagination_person"

    id: Mapped[int] = mapped_column(primary_key=True)
    team: Mapped[str | None]
    score: Mapped[int | None]


PEOPLE = [
    (1, "a", 10),
    (2, "b", None),
    (3, "a", None),
    (4, "b", 5),
    (5, "a", 10),
    (6, None, 7),
    (7, None, None),
    (8, "b", 5),
    (9, "a", 3),
    (10, None, 7),
]
PEOPLE_COLUMNS = {"id": Person.id, "team": Person.team, "score": Person.score}


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
        values = [getattr(last, t.field) for t in terms]
        cursor = decode_cursor(next_page_token(values, last.id, terms))


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
    token = next_page_token([T0], 5, (OrderField("due", descending=True),))

    assert_that(decode_cursor(token)).is_equal_to(
        Cursor((T0.isoformat(),), "5", "due desc")
    )


@pytest.mark.asyncio
async def test_a_token_for_another_order_by_is_invalid_cursor(session):
    cursor = Cursor(("1",), "1", "title")
    query = select(Task)

    with pytest.raises(InvalidCursor):
        keyset(
            query,
            columns=COLUMNS,
            terms=(),
            cursor=cursor,
            id_column=Task.id,
        )


@pytest.mark.asyncio
async def test_a_token_value_that_does_not_fit_the_column_is_invalid_cursor():
    cursor = Cursor(("not-a-date",), "1", "due")
    query = select(Task)
    terms = (OrderField("due"),)

    with pytest.raises(InvalidCursor):
        keyset(
            query,
            columns=COLUMNS,
            terms=terms,
            cursor=cursor,
            id_column=Task.id,
        )


def test_encode_cursor_round_trip_is_what_keyset_reads():
    assert_that(next_page_token((), 1, ())).is_equal_to(encode_cursor((), "1"))


# --- several terms, nullable columns --------------------------------------


async def _seed_people(session):
    session.add_all(Person(id=i, team=t, score=sc) for i, t, sc in PEOPLE)
    await session.commit()


async def _walk_people(session, terms, size):
    seen: list[int] = []
    cursor = None
    while True:
        stmt = keyset(
            select(Person),
            columns=PEOPLE_COLUMNS,
            terms=terms,
            cursor=cursor,
            id_column=Person.id,
        )
        rows = (await session.scalars(stmt.limit(size + 1))).all()
        page = rows[:size]
        seen += [p.id for p in page]
        if len(rows) <= size:
            return seen
        last = page[-1]
        values = [getattr(last, t.field) for t in terms]
        cursor = decode_cursor(next_page_token(values, last.id, terms))


def _expected_people(terms):
    """Independent oracle: stable sorts from the last term to the first, nulls last."""
    rows = list(PEOPLE)
    index = {"id": 0, "team": 1, "score": 2}
    keys = [(index[t.field], t.descending) for t in terms]
    if not any(i == 0 for i, _ in keys):
        keys.append((0, keys[-1][1] if keys else False))
    for i, descending in reversed(keys):
        present = sorted(
            (r for r in rows if r[i] is not None),
            key=lambda r: r[i],
            reverse=descending,
        )
        rows = present + [r for r in rows if r[i] is None]
    return [r[0] for r in rows]


def _every_ordering():
    for count in range(4):
        for fields in permutations(("team", "score", "id"), count):
            for directions in product((False, True), repeat=count):
                yield tuple(OrderField(f, d) for f, d in zip(fields, directions))


@pytest.mark.parametrize("size", [1, 3])
@pytest.mark.asyncio
async def test_paging_every_ordering_matches_one_unpaged_query(session, size):
    await _seed_people(session)

    for terms in _every_ordering():
        unpaged = (
            await session.scalars(
                keyset(
                    select(Person),
                    columns=PEOPLE_COLUMNS,
                    terms=terms,
                    cursor=None,
                    id_column=Person.id,
                )
            )
        ).all()
        assert [p.id for p in unpaged] == _expected_people(terms), terms
        assert await _walk_people(session, terms, size) == [p.id for p in unpaged], (
            terms
        )


@pytest.mark.asyncio
async def test_a_token_after_a_null_value_resumes_among_the_nulls(session):
    await _seed_people(session)
    terms = (OrderField("team"), OrderField("score", descending=True))
    cursor = decode_cursor(next_page_token(["a", None], 3, terms))

    stmt = keyset(
        select(Person),
        columns=PEOPLE_COLUMNS,
        terms=terms,
        cursor=cursor,
        id_column=Person.id,
    )

    assert_that([p.id for p in await session.scalars(stmt)]).is_equal_to(
        [8, 4, 2, 10, 6, 7]
    )


@pytest.mark.parametrize(
    "keys",
    [("x",), (1.5,), (True,), ({},)],
    ids=["str", "float", "bool", "object"],
)
def test_a_token_value_of_the_wrong_type_is_invalid_cursor(keys):
    cursor = Cursor(keys, "1", "score")  # type: ignore[arg-type]

    with pytest.raises(InvalidCursor):
        keyset(
            select(Person),
            columns=PEOPLE_COLUMNS,
            terms=(OrderField("score"),),
            cursor=cursor,
            id_column=Person.id,
        )


def test_a_null_for_the_id_term_is_invalid_cursor():
    cursor = Cursor((None,), "1", "id")

    with pytest.raises(InvalidCursor):
        keyset(
            select(Person),
            columns=PEOPLE_COLUMNS,
            terms=(OrderField("id"),),
            cursor=cursor,
            id_column=Person.id,
        )


def test_a_token_with_the_wrong_number_of_values_is_invalid_cursor():
    cursor = Cursor(("a",), "1", "team,score")

    with pytest.raises(InvalidCursor):
        keyset(
            select(Person),
            columns=PEOPLE_COLUMNS,
            terms=(OrderField("team"), OrderField("score")),
            cursor=cursor,
            id_column=Person.id,
        )


def test_next_page_token_keeps_json_types_and_writes_dates_as_iso():
    token = next_page_token([None, 3, "a", T0], 7, ())

    assert_that(decode_cursor(token).sort_keys).is_equal_to(
        (None, 3, "a", T0.isoformat())
    )
