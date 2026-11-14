from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from rn_forge.sqlalchemy import AuditMixin, Base, UpsertCounts, upsert
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
    ),
]

Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


class MeasurementProduct(AuditMixin, Base):
    __tablename__ = "measure_upsert_product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    qty: Mapped[int]


async def test_large_upsert(measure: Measure) -> None:
    row_count = 33_000
    rows = [{"sku": f"sku-{i}", "name": "item", "qty": 1} for i in range(row_count)]
    mixed = [
        {"sku": f"sku-{i}", "name": "item", "qty": 2 if i < 10 else 1}
        for i in range(row_count)
    ]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    statements = 0

    def count_statement(*_: object) -> None:
        nonlocal statements
        statements += 1

    async with engine.begin() as connection:
        await connection.run_sync(MeasurementProduct.__table__.create)
    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        async with AsyncSession(engine) as session:
            with measure(
                "sqlalchemy_upsert",
                {"initial_rows": row_count, "mixed_rows": row_count},
                "io",
            ) as counts:
                created = await upsert(
                    session,
                    MeasurementProduct,
                    rows,
                    key=["sku"],
                    fields=["name", "qty"],
                    actor="measure",
                )
                assert created == UpsertCounts(row_count, 0, 0)
                await session.commit()
                changed = await upsert(
                    session,
                    MeasurementProduct,
                    mixed,
                    key=["sku"],
                    fields=["name", "qty"],
                    actor="measure",
                )
                assert changed == UpsertCounts(0, 10, row_count - 10)
                await session.commit()
                counts["statements"] = statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
        await engine.dispose()
