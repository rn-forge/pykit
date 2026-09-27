"""A FastAPI app over SQLite, held to the web conformance table.

The `rn_forge.fastapi` adapters and `rn_forge.sqlalchemy` meet only here, in
test code; neither package imports the other.
"""

import re

import httpx
import pytest
from assertpy import assert_that
from fastapi import Depends, Query, Request, UploadFile
from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.fastapi import (
    AppConfig,
    FastApiApp,
    order_by_param,
    page_params,
)
from rn_forge.fastapi.transfer import problem_response, read_rows
from rn_forge.sqlalchemy import AuditMixin, Base, keyset, next_page_token, upsert
from rn_forge.web import Page, WireModel, import_report_body, row_errors_problem
from rn_forge.web.conformance import CASES, case_by_id, redact

pytestmark = pytest.mark.unit

CASE_IDS = [
    case.id
    for case in CASES
    if case.area == "pagination" or case.id.startswith("transfer.import-")
]


class Item(AuditMixin, Base):
    __tablename__ = "conformance_item"

    id: Mapped[str] = mapped_column(primary_key=True)


class Order(AuditMixin, Base):
    __tablename__ = "conformance_order"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    quantity: Mapped[int]


class OrderImport(WireModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    quantity: int = Field(alias="Quantity")

    @field_validator("quantity", mode="before")
    @classmethod
    def whole_number(cls, value):
        try:
            return int(value)
        except TypeError, ValueError:
            raise ValueError("Enter a whole number.") from None


def build_app(engine: AsyncEngine) -> FastApiApp:
    app = FastApiApp(AppConfig(tracing=False))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @app.get("/conformance/items")
    async def list_items(
        params=Depends(page_params(cap=2, default=2)),
        order=Depends(order_by_param(allowed=["id"])),
    ) -> Page[dict[str, str]]:
        size, cursor = params
        stmt = keyset(
            select(Item),
            columns={"id": Item.id},
            terms=order,
            cursor=cursor,
            id_column=Item.id,
        )
        async with sessions() as session:
            rows = (await session.scalars(stmt.limit(size + 1))).all()
        window = rows[:size]
        token = (
            next_page_token(window[-1].id, window[-1].id, order)
            if len(rows) > size
            else None
        )
        return Page[dict[str, str]](
            items=[{"id": row.id} for row in window], next_page_token=token
        )

    @app.post("/conformance/orders:import")
    async def import_orders(
        request: Request,
        file: UploadFile,
        validate_only: bool = Query(False, alias="validateOnly"),
    ):
        result = await read_rows(file, OrderImport)
        if result.errors:
            return problem_response(
                row_errors_problem(result.errors, instance=request.url.path)
            )
        async with sessions() as session:
            counts = await upsert(
                session,
                Order,
                [row.model_dump(by_alias=False) for row in result.valid],
                key=["id"],
                fields=["name", "quantity"],
                actor="conformance",
            )
            if validate_only:
                await session.rollback()
            else:
                await session.commit()
        return import_report_body(
            created=counts.created,
            updated=counts.updated,
            skipped=counts.skipped,
            validate_only=validate_only,
        )

    return app


async def issue(client: httpx.AsyncClient, case):
    spec = case.request
    headers = dict(spec.headers)
    if headers.get("Content-Type") == "multipart/form-data":
        del headers["Content-Type"]
        return await client.request(
            spec.method,
            spec.path,
            headers=headers,
            params=dict(spec.query),
            files={
                name: (name, value, "text/csv") for name, value in spec.body.items()
            },
        )
    return await client.request(
        spec.method, spec.path, headers=headers, params=dict(spec.query), json=spec.body
    )


@pytest.mark.parametrize("case_id", CASE_IDS)
@pytest.mark.asyncio
async def test_sqlalchemy_backed_fastapi_conforms(engine, session, case_id):
    session.add_all(Item(id=str(i)) for i in (1, 2, 3))
    await session.commit()
    case = case_by_id(case_id)
    transport = httpx.ASGITransport(app=build_app(engine), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        for prerequisite in case.depends_on:
            await issue(client, case_by_id(prerequisite))

        response = await issue(client, case)

    assert_that(response.status_code).described_as("status").is_equal_to(
        case.expect_status
    )
    for name, value in case.expect_headers.items():
        assert_that(response.headers.get(name)).described_as(name).is_equal_to(value)
    for name, pattern in case.expect_header_patterns.items():
        assert_that(re.fullmatch(pattern, response.headers[name])).is_not_none()
    body = response.json() if response.content else {}
    assert_that(redact(body)).is_equal_to(dict(case.expect_body))


def test_the_selected_cases_include_the_order_by_and_import_cases():
    assert_that(CASE_IDS).contains(
        "pagination.order-by-descending-binds-the-token",
        "pagination.order-by-unlisted-field-is-400",
        "pagination.token-under-a-different-order-by-is-400",
        "transfer.import-report-counts-and-validate-only",
        "transfer.import-row-errors-are-422-pointers",
    )


@pytest.mark.asyncio
async def test_a_real_import_persists_and_a_repeat_is_skipped(engine, session):
    transport = httpx.ASGITransport(app=build_app(engine))
    upload = {"file": ("o.csv", b"id,name,Quantity\n2,gadget,3\n", "text/csv")}
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        first = await client.post("/conformance/orders:import", files=upload)
        second = await client.post("/conformance/orders:import", files=upload)

    assert_that(first.json()["created"]).is_equal_to(1)
    assert_that(second.json()["skipped"]).is_equal_to(1)
    assert_that((await session.scalars(select(Order))).all()).is_length(1)
