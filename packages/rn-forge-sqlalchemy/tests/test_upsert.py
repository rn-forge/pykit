from datetime import UTC, datetime

import pytest
from assertpy import assert_that
from sqlalchemy import UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.sqlalchemy import AuditMixin, Base, UpsertCounts, upsert

pytestmark = pytest.mark.unit


class Product(AuditMixin, Base):
    __tablename__ = "upsert_product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    qty: Mapped[int]


async def _load(session) -> dict[str, Product]:
    session.expire_all()
    return {p.sku: p for p in await session.scalars(select(Product))}


def _rows(*skus: str, name: str = "n", qty: int = 1):
    return [{"sku": s, "name": name, "qty": qty} for s in skus]


async def _upsert(session, rows, actor="ann"):
    return await upsert(
        session, Product, rows, key=["sku"], fields=["name", "qty"], actor=actor
    )


@pytest.mark.asyncio
async def test_counts_created_updated_and_skipped(session):
    await _upsert(session, _rows("a", "b", "c"))
    await session.commit()

    counts = await _upsert(
        session, [*_rows("a"), *_rows("b", name="changed"), *_rows("d")]
    )

    assert_that(counts).is_equal_to(UpsertCounts(created=1, updated=1, skipped=1))
    products = await _load(session)
    assert_that(products["b"].name).is_equal_to("changed")
    assert_that(products).contains_key("d")


@pytest.mark.asyncio
async def test_audit_stamps_on_insert_and_on_update(session):
    await _upsert(session, _rows("a"), actor="ann")
    await session.commit()
    first = (await _load(session))["a"]
    created = first.create_time

    await _upsert(session, _rows("a", qty=2), actor="bob")
    await session.commit()

    second = (await _load(session))["a"]
    assert_that((second.created_by, second.updated_by)).is_equal_to(("ann", "bob"))
    assert_that(second.create_time).is_equal_to(created)
    assert_that(second.update_time).is_greater_than(created)
    assert_that(second.update_time.tzinfo).is_equal_to(UTC)


@pytest.mark.asyncio
async def test_a_skipped_row_is_not_rewritten(session):
    await _upsert(session, _rows("a"), actor="ann")
    await session.commit()

    await _upsert(session, _rows("a"), actor="bob")
    await session.commit()

    assert_that((await _load(session))["a"].updated_by).is_equal_to("ann")


@pytest.mark.asyncio
async def test_rolling_back_after_the_call_writes_nothing(session):
    counts = await _upsert(session, _rows("a", "b"))
    await session.rollback()

    assert_that(counts.created).is_equal_to(2)
    assert_that(await _load(session)).is_empty()


@pytest.mark.asyncio
async def test_a_duplicate_key_in_the_input_raises(session):
    with pytest.raises(ValueError, match="duplicate key"):
        await _upsert(session, _rows("a", "a"))


@pytest.mark.asyncio
async def test_a_missing_column_raises(session):
    with pytest.raises(ValueError, match="qty"):
        await _upsert(session, [{"sku": "a", "name": "n"}])


@pytest.mark.asyncio
async def test_a_key_set_larger_than_sqlites_parameter_limit(session):
    skus = [f"s{i}" for i in range(33_000)]
    counts = await _upsert(session, _rows(*skus))
    await session.commit()

    again = await _upsert(session, [*_rows(*skus[:10], qty=2), *_rows(*skus[10:])])

    assert_that(counts).is_equal_to(UpsertCounts(33_000, 0, 0))
    assert_that(again).is_equal_to(UpsertCounts(0, 10, 32_990))


class Line(AuditMixin, Base):
    __tablename__ = "upsert_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str]
    line_no: Mapped[int]
    sku: Mapped[str]

    __table_args__ = (UniqueConstraint("order_no", "line_no"),)


@pytest.mark.asyncio
async def test_a_composite_key(session):
    rows = [{"order_no": "o", "line_no": i, "sku": "x"} for i in (1, 2)]
    line_key = dict(key=["order_no", "line_no"], fields=["sku"], actor="ann")
    await upsert(session, Line, rows, **line_key)
    counts = await upsert(
        session, Line, [*rows[:1], {**rows[1], "sku": "y"}], **line_key
    )

    assert_that(counts).is_equal_to(UpsertCounts(0, 1, 1))
