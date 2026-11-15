"""Measure upsert resource use across row shapes and key types."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from rn_forge.sqlalchemy import AuditMixin, Base, UpsertCounts, upsert
from sqlalchemy import UniqueConstraint, event, select
from sqlalchemy.orm import Mapped, mapped_column

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
    ),
]


class ResourceProduct(AuditMixin, Base):
    __tablename__ = "measure_resource_upsert_product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    qty: Mapped[int]


class ResourceLine(AuditMixin, Base):
    __tablename__ = "measure_resource_upsert_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str]
    line_no: Mapped[int]
    sku: Mapped[str]

    __table_args__ = (UniqueConstraint("order_no", "line_no"),)


@pytest.mark.parametrize("key_shape", ["single", "composite"])
@pytest.mark.parametrize(
    "shape",
    [
        "empty",
        "created-2",
        "unchanged-2",
        "mixed-3",
        "duplicate-2",
        "rollback-3",
        "created-33000",
        "mixed-33000",
    ],
)
async def test_upsert_resource_baselines(
    session, engine, measure: Measure, key_shape, shape
):
    model = ResourceProduct if key_shape == "single" else ResourceLine
    key = ["sku"] if key_shape == "single" else ["order_no", "line_no"]
    fields = ["name", "qty"] if key_shape == "single" else ["sku"]

    def rows(size, value="n"):
        if key_shape == "single":
            return [
                {"sku": f"baseline-{i}", "name": value, "qty": 1} for i in range(size)
            ]
        return [
            {"order_no": "baseline", "line_no": i, "sku": value} for i in range(size)
        ]

    async def call(data, actor="ann"):
        return await upsert(session, model, data, key=key, fields=fields, actor=actor)

    async def load():
        session.expire_all()
        return (await session.scalars(select(model).order_by(model.id))).all()

    expected = {
        "empty": UpsertCounts(0, 0, 0),
        "created-2": UpsertCounts(2, 0, 0),
        "unchanged-2": UpsertCounts(0, 0, 2),
        "mixed-3": UpsertCounts(1, 1, 1),
        "rollback-3": UpsertCounts(0, 3, 0),
        "created-33000": UpsertCounts(33_000, 0, 0),
        "mixed-33000": UpsertCounts(0, 10, 32_990),
    }
    reads = (33_000 + 900 // len(key) - 1) // (900 // len(key))
    statements = 0
    active = False

    def count_statement(*_):
        nonlocal statements
        if active:
            statements += 1

    async def run_measure(label, operation, input_rows):
        nonlocal active, statements
        statements = 0
        with measure(
            "sqlalchemy_upsert_resources",
            {
                "key_shape": key_shape,
                "dialect": engine.dialect.name,
                "shape": label,
                "sqlite_version": sqlite3.sqlite_version,
                "rows": input_rows,
            },
            "io",
        ) as counts:
            active = True
            try:
                result = await operation()
            finally:
                active = False
            counts["statements"] = statements
        return result, statements

    if shape == "unchanged-2" or shape == "mixed-3":
        await call(rows(2))
        await session.commit()
        before = [
            (row.create_time, row.created_by, row.update_time) for row in await load()
        ]
    elif shape == "rollback-3":
        await call(rows(3))
        await session.commit()
    elif shape == "mixed-33000":
        await call(rows(33_000))
        await session.commit()

    if shape in ("created-33000", "mixed-33000"):
        large = rows(33_000)
        if shape == "mixed-33000":
            large[:10] = rows(10, "changed")

    async def operation():
        if shape == "empty":
            return await call([])
        if shape == "created-2":
            return await call(rows(2))
        if shape == "unchanged-2":
            return await call(rows(2), actor="bob")
        if shape == "mixed-3":
            return await call([rows(1, "changed")[0], *rows(3)[1:]], actor="bob")
        if shape == "duplicate-2":
            with pytest.raises(ValueError, match="duplicate key"):
                await call(rows(1) * 2)
            return None
        if shape == "rollback-3":
            return await call(rows(3, "rollback"))
        return await call(large)

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        input_rows = {
            "empty": 0,
            "created-2": 2,
            "unchanged-2": 2,
            "mixed-3": 3,
            "duplicate-2": 2,
            "rollback-3": 3,
            "created-33000": 33_000,
            "mixed-33000": 33_000,
        }[shape]
        result, statement_count = await run_measure(shape, operation, input_rows)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)

    assert result == expected.get(shape)
    expected_statements = {
        "empty": 0,
        "created-2": 2,
        "unchanged-2": 1,
        "mixed-3": 2,
        "duplicate-2": 0,
        "rollback-3": 2,
        "created-33000": reads + 1,
        "mixed-33000": reads + 1,
    }[shape]
    assert statement_count == expected_statements

    if shape == "created-2":
        await session.commit()
        assert len(await load()) == 2
    elif shape == "unchanged-2":
        assert [
            (row.create_time, row.created_by, row.update_time) for row in await load()
        ] == before
    elif shape == "mixed-3":
        await session.commit()
        after = await load()
        assert len(after) == 3
        assert (after[0].create_time, after[0].created_by) == before[0][:2]
        assert after[0].updated_by == "bob"
        assert after[1].update_time == before[1][2]
    elif shape == "duplicate-2":
        assert len(await load()) == 0
    elif shape == "rollback-3":
        await session.rollback()
        restored = await load()
        assert [getattr(row, fields[0]) for row in restored] == ["n", "n", "n"]
    elif shape == "created-33000":
        await session.commit()
        assert len(await load()) == 33_000
    elif shape == "mixed-33000":
        await session.rollback()
        assert len(await load()) == 33_000
