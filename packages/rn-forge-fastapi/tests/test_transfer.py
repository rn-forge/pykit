import io
from datetime import date

import pytest
from assertpy import assert_that
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, computed_field
from starlette.datastructures import Headers

from rn_forge.fastapi.transfer import read_rows, tabular_format, tabular_response
from rn_forge.web.transfer import TABULAR_FORMATS

pytestmark = pytest.mark.unit


class Line(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str = Field(serialization_alias="SKU")
    qty: int = Field(serialization_alias="Quantity")
    due: date = Field(serialization_alias="Due")

    @computed_field(alias="Label")
    @property
    def label(self) -> str:
        return f"{self.sku}x{self.qty}"


class Item:
    sku, qty, due = "a", 2, date(2026, 1, 2)


def upload(name: str, content: bytes, content_type: str | None = None) -> UploadFile:
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(io.BytesIO(content), filename=name, headers=headers)


def client(allowed=("csv", "xlsx")) -> TestClient:
    app = FastAPI()

    @app.get("/x")
    def route(fmt=__import__("fastapi").Depends(tabular_format(allowed))):
        return {"fmt": fmt.extension if fmt else None}

    return TestClient(app)


def test_the_dependency_reads_accept_and_the_format_param():
    c = client()
    assert_that(c.get("/x", headers={"Accept": "text/csv"}).json()).is_equal_to(
        {"fmt": "csv"}
    )
    assert_that(c.get("/x", params={"format": "xlsx"}).json()).is_equal_to(
        {"fmt": "xlsx"}
    )
    assert_that(c.get("/x").json()).is_equal_to({"fmt": None})
    assert_that(c.get("/x", params={"format": "tsv"}).json()).is_equal_to({"fmt": None})


@pytest.mark.asyncio
async def test_csv_headers_are_aliases_and_computed_fields():
    response = await tabular_response([Item()], Line, TABULAR_FORMATS["csv"], "l.csv")
    assert_that(response.media_type).is_equal_to("text/csv")
    assert_that(response.headers["content-disposition"]).contains('filename="l.csv"')

    app = FastAPI()

    async def route():
        return await tabular_response([Item()], Line, TABULAR_FORMATS["csv"], "l.csv")

    app.get("/l")(route)
    body = TestClient(app).get("/l").text
    assert_that(body).is_equal_to("SKU,Quantity,Due,Label\r\na,2,2026-01-02,ax2\r\n")


@pytest.mark.asyncio
async def test_xlsx_round_trips_through_tablib():
    import tablib

    response = await tabular_response([Item()], Line, TABULAR_FORMATS["xlsx"], "l.xlsx")
    dataset = tablib.Dataset().load(bytes(response.body), format="xlsx")
    assert_that(dataset.headers).is_equal_to(["SKU", "Quantity", "Due", "Label"])
    assert_that(dataset[0][:2]).is_equal_to(("a", 2))


@pytest.mark.asyncio
async def test_tsv_is_built_with_tablib():
    response = await tabular_response([Item()], Line, TABULAR_FORMATS["tsv"], "l.tsv")
    assert_that(bytes(response.body).decode()).starts_with("SKU\tQuantity")


class Row(BaseModel):
    name: str
    qty: int = Field(alias="Quantity")


@pytest.mark.asyncio
async def test_read_rows_separates_valid_rows_from_cell_errors():
    result = await read_rows(upload("r.csv", b"name,Quantity\nok,1\nbad,x\n,3\n"), Row)
    assert_that([r.name for r in result.valid]).is_equal_to(["ok", ""])
    assert_that([(e.row, e.field) for e in result.errors]).is_equal_to(
        [(1, "Quantity")]
    )


@pytest.mark.asyncio
async def test_read_rows_reports_a_missing_column_against_the_row():
    result = await read_rows(upload("r.csv", b"name\nok\n"), Row)
    assert_that([(e.row, e.field) for e in result.errors]).is_equal_to(
        [(0, "Quantity")]
    )


@pytest.mark.asyncio
async def test_read_rows_reads_xlsx():
    import tablib

    data = tablib.Dataset(["a", 1], headers=["name", "Quantity"]).export("xlsx")
    result = await read_rows(upload("r.xlsx", data), Row)
    assert_that(result.errors).is_empty()
    assert_that(result.valid[0].qty).is_equal_to(1)


@pytest.mark.asyncio
async def test_read_rows_falls_back_to_the_content_type():
    result = await read_rows(upload("file", b"name,Quantity\na,1\n", "text/csv"), Row)
    assert_that(result.valid).is_length(1)


@pytest.mark.asyncio
async def test_read_rows_rejects_an_unknown_type():
    with pytest.raises(ValueError, match="Unsupported"):
        await read_rows(upload("r.pdf", b""), Row)
