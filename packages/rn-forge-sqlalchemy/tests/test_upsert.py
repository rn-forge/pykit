import asyncio
import importlib
from datetime import UTC

import pytest
from assertpy import assert_that
from rn_forge.sqlalchemy import AuditMixin, Base, UpsertCounts, upsert
from sqlalchemy import UniqueConstraint, event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

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
    rows = _rows("a", "a")
    with pytest.raises(ValueError, match="duplicate key"):
        await _upsert(session, rows)


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
    line_key = {"key": ["order_no", "line_no"], "fields": ["sku"], "actor": "ann"}
    await upsert(session, Line, rows, **line_key)
    counts = await upsert(
        session, Line, [*rows[:1], {**rows[1], "sku": "y"}], **line_key
    )

    assert_that(counts).is_equal_to(UpsertCounts(0, 1, 1))


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_competing_writer_between_read_and_write_miscounts(
    session, engine, monkeypatch, request
):
    upsert_module = importlib.import_module("rn_forge.sqlalchemy.upsert")
    original_existing = upsert_module._existing
    competing_session = AsyncSession(engine, expire_on_commit=False)
    raced = False

    async def insert_between_read_and_write(*args, **kwargs):
        nonlocal raced
        existing = await original_existing(*args, **kwargs)
        if not raced:
            raced = True
            await _upsert(competing_session, _rows("race"), actor="writer B")
            await competing_session.commit()
        return existing

    monkeypatch.setattr(upsert_module, "_existing", insert_between_read_and_write)
    try:
        counts = await _upsert(session, _rows("race", name="writer A"))
        await session.commit()
    finally:
        await competing_session.close()

    products = await _load(session)
    assert raced
    assert_that(len(products)).is_equal_to(1)
    assert_that(products["race"].name).is_equal_to("writer A")
    assert_that((products["race"].created_by, products["race"].updated_by)).is_equal_to(
        ("writer B", "ann")
    )
    assert counts == UpsertCounts(1, 0, 0)
    request.node.add_marker(
        pytest.mark.xfail(
            strict=True,
            raises=AssertionError,
            reason="S22.11.1: pre-write snapshot reports a creation for an update",
        )
    )
    assert counts == UpsertCounts(0, 1, 0)


@pytest.mark.asyncio
async def test_two_sessions_upserting_the_same_new_keys(session, engine, monkeypatch):
    upsert_module = importlib.import_module("rn_forge.sqlalchemy.upsert")
    original_existing = upsert_module._existing
    both_read = asyncio.Event()
    readers = 0

    async def synchronize_reads(*args, **kwargs):
        nonlocal readers
        existing = await original_existing(*args, **kwargs)
        readers += 1
        if readers == 2:
            both_read.set()
        await asyncio.wait_for(both_read.wait(), timeout=10)
        return existing

    monkeypatch.setattr(upsert_module, "_existing", synchronize_reads)

    async def run(actor):
        async with AsyncSession(engine, expire_on_commit=False) as current:
            counts = await _upsert(current, _rows("shared"), actor=actor)
            await current.commit()
            return ("success", counts)

    outcomes = await asyncio.gather(run("first"), run("second"))
    products = await _load(session)
    assert outcomes == [("success", UpsertCounts(1, 0, 0))] * 2
    assert_that(len(products)).is_equal_to(1)
    assert products["shared"].name == "n"
    assert products["shared"].qty == 1
    assert {products["shared"].created_by, products["shared"].updated_by} == {
        "first",
        "second",
    }


@pytest.mark.asyncio
async def test_serial_upserts_report_exact_counts(session):
    first = await _upsert(session, _rows("serial"))
    await session.commit()
    second = await _upsert(session, _rows("serial", name="changed"))
    await session.commit()

    assert_that(first).is_equal_to(UpsertCounts(1, 0, 0))
    assert_that(second).is_equal_to(UpsertCounts(0, 1, 0))


@pytest.mark.asyncio
async def test_empty_rows_runs_no_query(session, engine):
    statements = 0

    def count_statement(*_):
        nonlocal statements
        statements += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        counts = await _upsert(session, [])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)

    assert_that(counts).is_equal_to(UpsertCounts(0, 0, 0))
    assert_that(statements).is_equal_to(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [[], _rows("a")])
async def test_an_empty_key_raises_value_error(session, rows):
    with pytest.raises(ValueError, match="key.*must not be empty"):
        await upsert(session, Product, rows, key=[], fields=["name"], actor="ann")
