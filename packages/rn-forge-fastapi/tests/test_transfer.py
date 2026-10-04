import io
from datetime import date

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, computed_field
from starlette.datastructures import Headers

from rn_forge.fastapi import AppConfig, FastApiApp
from rn_forge.fastapi.transfer import (
    batch_create_router,
    batch_delete_router,
    batch_get_router,
    batch_update_router,
    import_router,
    import_template_router,
    read_rows,
    tabular_export,
    tabular_format,
    tabular_response,
)
from rn_forge.web import (
    ImportCounts,
    ItemsDenied,
    PermissionDenied,
    RowError,
    RowsInvalid,
)
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
    pdf = upload("r.pdf", b"")
    with pytest.raises(ValueError, match="Unsupported"):
        await read_rows(pdf, Row)


@pytest.mark.asyncio
async def test_read_rows_counts_every_data_row_and_names_the_unsupported_types():
    result = await read_rows(upload("r.csv", b"name,Quantity\nok,1\nbad,x\n"), Row)
    assert_that(result.total).is_equal_to(2)
    with pytest.raises(ValueError) as unsupported:
        await read_rows(upload("r.pdf", b""), Row)
    assert_that(str(unsupported.value)).is_equal_to(
        "Unsupported file type; use one of: csv, tsv, xlsx."
    )
    with pytest.raises(ValueError) as restricted:
        await read_rows(upload("r.tsv", b""), Row, formats=("csv",))
    assert_that(str(restricted.value)).is_equal_to(
        "Unsupported file type; use one of: csv."
    )


@pytest.mark.asyncio
async def test_read_rows_names_the_extension_it_could_not_read():
    with pytest.raises(ValueError) as unreadable:
        await read_rows(upload("r.xlsx", b"not a workbook"), Row)
    assert_that(str(unreadable.value)).is_equal_to(
        "The file could not be read as xlsx."
    )


@pytest.mark.asyncio
async def test_tabular_export_applies_the_cap_to_the_rows():
    csv = TABULAR_FORMATS["csv"]
    rows = [Item(), Item()]
    capped = await tabular_export(
        rows, Line, csv, "l.csv", max_rows=1, instance="/lines"
    )
    assert_that(capped.status_code).is_equal_to(422)
    assert_that(bytes(capped.body).decode()).contains(
        "The export exceeds the limit of 1 rows; narrow the filter."
    )
    within = await tabular_export(rows, Line, csv, "l.csv", max_rows=2, instance="/l")
    assert_that(within.media_type).is_equal_to("text/csv")
    unlimited = await tabular_export(rows, Line, csv, "l.csv", instance="/l")
    assert_that(unlimited.status_code).is_equal_to(200)


class OrderImport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    name: str
    quantity: int = Field(alias="Quantity")


class OrderCreate(BaseModel):
    name: str
    note: str | None = None


class OrderRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        alias_generator=lambda name: name.upper(),
    )

    id: str
    name: str


class Order:
    def __init__(self, id: str, name: str, quantity: int = 0) -> None:
        self.id, self.name, self.quantity = id, name, quantity


class Store:
    """Records every call; raises what the test sets."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.rows_raised: Exception | None = None
        self.denied: Exception | None = None
        self.present = {"1", "2"}

    async def import_rows(self, rows, *, validate_only):
        self.calls.append(("import_rows", (len(rows), validate_only)))
        if self.rows_raised:
            raise self.rows_raised
        return ImportCounts(created=len(rows), updated=1, skipped=2)

    async def rows(self):
        self.calls.append(("rows", None))
        return [Order("1", "widget", 3), Order("2", "gadget")]

    async def create_many(self, items):
        self.calls.append(("create_many", [i.name for i in items]))
        if self.denied:
            raise self.denied
        return [Order(str(n), i.name) for n, i in enumerate(items, 1)]

    async def find(self, ids):
        self.calls.append(("find", list(ids)))
        return [i for i in ids if i in self.present]

    async def delete_many(self, ids):
        self.calls.append(("delete_many", list(ids)))
        if self.denied:
            raise self.denied


def deny_everything():
    raise PermissionDenied("Not yours")


def resource(*, cap=None, guard=None, **import_options):
    store = Store()
    dependencies = [Depends(guard)] if guard else []
    app = FastApiApp(AppConfig())

    def get_store() -> Store:
        return store

    app.include_router(
        import_router(
            "/orders",
            model=OrderImport,
            store=get_store,
            max_rows=cap,
            dependencies=dependencies,
            **import_options,
        )
    )
    app.include_router(
        import_template_router(
            "/orders",
            model=OrderImport,
            source=get_store,
            max_rows=cap,
            dependencies=dependencies,
            **import_options,
        )
    )
    app.include_router(
        batch_create_router(
            "/orders",
            model=OrderCreate,
            response_model=OrderRead,
            resource_name="orders",
            store=get_store,
            max_rows=cap,
            dependencies=dependencies,
        )
    )
    app.include_router(
        batch_delete_router(
            "/orders",
            resource_label="Order",
            store=get_store,
            max_rows=cap,
            dependencies=dependencies,
        )
    )
    return TestClient(app, raise_server_exceptions=False), store, app


CSV = b"id,name,Quantity\n1,a,1\n2,b,2\n"


def post_file(client, content=CSV, name="o.csv", **params):
    return client.post(
        "/orders:import", params=params, files={"file": (name, content, "text/csv")}
    )


def pointers(response):
    return [(e["pointer"], e["detail"]) for e in response.json()["errors"]]


def test_import_upserts_through_the_store_and_reports_its_counts():
    client, store, _ = resource()
    response = post_file(client, validateOnly="TRUE")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to(
        {"created": 2, "updated": 1, "skipped": 2, "validateOnly": True}
    )
    assert_that(store.calls).is_equal_to([("import_rows", (2, True))])
    post_file(client, validateOnly="no")
    assert_that(store.calls[-1]).is_equal_to(("import_rows", (2, False)))


def test_import_reads_xlsx():
    import tablib

    client, store, _ = resource()
    data = tablib.Dataset(["1", "a", 1], headers=["id", "name", "Quantity"]).export(
        "xlsx"
    )
    assert_that(post_file(client, data, "o.xlsx").status_code).is_equal_to(200)
    assert_that(store.calls).is_length(1)


def test_import_without_a_file_is_a_required_field():
    client, store, _ = resource()
    response = client.post("/orders:import", files={"other": ("o.csv", CSV)})
    assert_that(response.status_code).is_equal_to(422)
    assert_that(pointers(response)).is_equal_to([("/file", "This field is required.")])
    assert_that(store.calls).is_empty()


def test_import_rejects_a_type_outside_formats():
    client, store, _ = resource(formats=("csv",))
    for content, name in ((CSV, "o.xlsx"), (b"", "o.pdf")):
        response = post_file(client, content, name)
        assert_that(response.status_code).is_equal_to(422)
        assert_that(pointers(response)).is_equal_to(
            [("/file", "Unsupported file type; use one of: csv.")]
        )
    assert_that(store.calls).is_empty()


def test_import_rejects_an_unreadable_file():
    client, store, _ = resource()
    response = post_file(client, b"not a workbook", "o.xlsx")
    assert_that(response.status_code).is_equal_to(422)
    assert_that(pointers(response)).is_equal_to(
        [("/file", "The file could not be read as xlsx.")]
    )
    assert_that(store.calls).is_empty()


def test_import_over_the_cap_is_a_problem_without_errors():
    client, store, _ = resource(cap=1)
    response = post_file(client)
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to(
        "The import exceeds the limit of 1 rows."
    )
    assert_that(response.json()).does_not_contain_key("errors")
    assert_that(store.calls).is_empty()


def test_import_row_errors_never_reach_the_store():
    client, store, _ = resource()
    response = post_file(client, b"id,name,Quantity\n1,a,x\n2,b,2\n")
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to("One or more rows are invalid.")
    assert_that([p for p, _ in pointers(response)]).is_equal_to(["/rows/0/Quantity"])
    assert_that(store.calls).is_empty()


def test_import_renders_rows_a_store_rejects():
    client, store, _ = resource()
    store.rows_raised = RowsInvalid([RowError(1, "id", "Unknown parent.")])
    response = post_file(client)
    assert_that(response.status_code).is_equal_to(422)
    assert_that(pointers(response)).is_equal_to([("/rows/1/id", "Unknown parent.")])


def test_every_route_runs_its_dependencies_first():
    client, store, _ = resource(guard=deny_everything)
    responses = [
        post_file(client),
        client.get("/orders:importTemplate", params={"prefill": "true"}),
        client.post("/orders:batchCreate", json={"requests": [{"name": "a"}]}),
        client.post("/orders:batchDelete", json={"ids": ["1"]}),
        client.post("/orders:batchDelete", json={}),
    ]
    assert_that([r.status_code for r in responses]).is_equal_to([403] * 5)
    assert_that(store.calls).is_empty()


def test_template_is_the_import_columns_and_round_trips():
    client, store, _ = resource()
    response = client.get("/orders:importTemplate", headers={"Accept": "text/csv"})
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.text).is_equal_to("id,name,Quantity\r\n")
    assert_that(response.headers["content-disposition"]).is_equal_to(
        'attachment; filename="import-template.csv"; '
        "filename*=UTF-8''import-template.csv"
    )
    assert_that(store.calls).is_empty()
    prefilled = client.get(
        "/orders:importTemplate", params={"prefill": "1", "format": "csv"}
    )
    assert_that(prefilled.text).is_equal_to(
        "id,name,Quantity\r\n1,widget,3\r\n2,gadget,0\r\n"
    )
    assert_that(post_file(client, prefilled.content).status_code).is_equal_to(200)


def test_template_defaults_to_the_first_format_and_honours_the_request():
    client, _, _ = resource(formats=("xlsx", "csv"))
    default = client.get("/orders:importTemplate")
    assert_that(default.headers["content-disposition"]).contains("import-template.xlsx")
    asked = client.get("/orders:importTemplate", params={"format": "csv"})
    assert_that(asked.headers["content-disposition"]).contains("import-template.csv")


def test_template_prefill_over_the_cap_is_the_export_cap_problem():
    client, _, _ = resource(cap=1)
    assert_that(client.get("/orders:importTemplate").status_code).is_equal_to(200)
    response = client.get("/orders:importTemplate", params={"prefill": "true"})
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to(
        "The export exceeds the limit of 1 rows; narrow the filter."
    )


def test_batch_create_returns_the_created_objects_by_alias():
    client, store, _ = resource()
    response = client.post(
        "/orders:batchCreate", json={"requests": [{"name": "a"}, {"name": "b"}]}
    )
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to(
        {"orders": [{"ID": "1", "NAME": "a"}, {"ID": "2", "NAME": "b"}]}
    )
    assert_that(store.calls).is_equal_to([("create_many", ["a", "b"])])


@pytest.mark.parametrize(
    ("body", "pointer", "detail"),
    [
        ({}, "/requests", "This field is required."),
        ({"requests": []}, "/requests", "A non-empty list is required."),
        ({"requests": "x"}, "/requests", "A non-empty list is required."),
        ([1], "/requests", "This field is required."),
    ],
)
def test_batch_create_checks_the_raw_member_first(body, pointer, detail):
    client, store, _ = resource()
    response = client.post("/orders:batchCreate", json=body)
    assert_that(response.status_code).is_equal_to(422)
    assert_that(pointers(response)).is_equal_to([(pointer, detail)])
    assert_that(store.calls).is_empty()


def test_batch_create_over_the_cap_beats_item_validation():
    client, store, _ = resource(cap=1)
    response = client.post("/orders:batchCreate", json={"requests": [{}, {}]})
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to(
        "The batch exceeds the limit of 1 rows."
    )
    assert_that(response.json()).does_not_contain_key("errors")
    assert_that(store.calls).is_empty()


def test_batch_create_reports_every_invalid_item():
    client, store, _ = resource()
    response = client.post(
        "/orders:batchCreate",
        json={"requests": [{}, {"name": "ok"}, {"name": "x", "note": 5}, {}]},
    )
    assert_that(response.status_code).is_equal_to(422)
    assert_that([p for p, _ in pointers(response)]).is_equal_to(
        ["/requests/0/name", "/requests/2/note", "/requests/3/name"]
    )
    assert_that(pointers(response)[0][1]).is_equal_to("This field is required.")
    assert_that(store.calls).is_empty()


def test_batch_create_renders_items_a_store_denies():
    client, store, _ = resource()
    store.denied = ItemsDenied(
        {"1": ["You may not create this order."]}, root="requests"
    )
    response = client.post(
        "/orders:batchCreate", json={"requests": [{"name": "a"}, {"name": "b"}]}
    )
    assert_that(response.status_code).is_equal_to(403)
    assert_that(pointers(response)).is_equal_to(
        [("/requests/1", "You may not create this order.")]
    )


def test_batch_delete_accepts_string_and_integer_ids():
    client, store, _ = resource()
    response = client.post("/orders:batchDelete", json={"ids": [1, "2"]})
    assert_that(response.status_code).is_equal_to(204)
    assert_that(response.content).is_equal_to(b"")
    assert_that(store.calls).is_equal_to(
        [("find", ["1", "2"]), ("delete_many", ["1", "2"])]
    )


def test_batch_delete_names_the_first_missing_id_and_deletes_nothing():
    client, store, _ = resource()
    response = client.post("/orders:batchDelete", json={"ids": ["1", 9, "8"]})
    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.json()["detail"]).is_equal_to("Order 9 not found")
    assert_that([name for name, _ in store.calls]).is_equal_to(["find"])


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({}, "This field is required."),
        ({"ids": []}, "A non-empty list is required."),
    ],
)
def test_batch_delete_requires_a_non_empty_ids_list(body, detail):
    client, store, _ = resource()
    response = client.post("/orders:batchDelete", json=body)
    assert_that(response.status_code).is_equal_to(422)
    assert_that(pointers(response)).is_equal_to([("/ids", detail)])
    assert_that(store.calls).is_empty()


def test_batch_delete_over_the_cap_is_a_problem_without_errors():
    client, store, _ = resource(cap=1)
    response = client.post("/orders:batchDelete", json={"ids": ["1", "2"]})
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to(
        "The batch exceeds the limit of 1 rows."
    )
    assert_that(store.calls).is_empty()


def test_batch_delete_renders_ids_a_store_denies():
    client, store, _ = resource()
    store.denied = ItemsDenied({"0": ["In use."]}, root="ids")
    response = client.post("/orders:batchDelete", json={"ids": ["1"]})
    assert_that(response.status_code).is_equal_to(403)
    assert_that(pointers(response)).is_equal_to([("/ids/0", "In use.")])


def test_openapi_describes_the_four_routes():
    _, _, app = resource()
    paths = app.openapi()["paths"]
    operations = {
        path: next(iter(item.values()))["operationId"]
        for path, item in paths.items()
        if path.startswith("/orders")
    }
    assert_that(operations).is_equal_to(
        {
            "/orders:import": "ordersImport",
            "/orders:importTemplate": "ordersImportTemplate",
            "/orders:batchCreate": "ordersBatchCreate",
            "/orders:batchDelete": "ordersBatchDelete",
        }
    )
    schemas = app.openapi()["components"]["schemas"]
    upload_body = paths["/orders:import"]["post"]["requestBody"]["content"]
    assert_that(upload_body).contains_key("multipart/form-data")
    form = schemas[upload_body["multipart/form-data"]["schema"]["$ref"].rsplit("/")[-1]]
    assert_that(form["properties"]["file"]).contains_entry(
        {"type": "string"}, {"contentMediaType": "application/octet-stream"}
    )

    create = paths["/orders:batchCreate"]["post"]
    request = create["requestBody"]["content"]["application/json"]["schema"]
    request_schema = schemas[request["$ref"].rsplit("/")[-1]]
    assert_that(request_schema["properties"]["requests"]["items"]).is_equal_to(
        {"$ref": "#/components/schemas/OrderCreate"}
    )
    response = create["responses"]["200"]["content"]["application/json"]["schema"]
    response_schema = schemas[response["$ref"].rsplit("/")[-1]]
    assert_that(response_schema["properties"]["orders"]["items"]).is_equal_to(
        {"$ref": "#/components/schemas/OrderRead"}
    )

    delete = paths["/orders:batchDelete"]["post"]
    ids = delete["requestBody"]["content"]["application/json"]["schema"]
    ids_schema = schemas[ids["$ref"].rsplit("/")[-1]]
    assert_that(ids_schema["properties"]["ids"]["items"]).is_equal_to(
        {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    )
    assert_that(set(delete["responses"])).contains("204")


def test_the_problem_repair_declares_403_404_and_422_on_every_route():
    _, _, app = resource()
    for item in app.openapi()["paths"].values():
        responses = next(iter(item.values()))["responses"]
        for status in ("403", "404", "422"):
            assert_that(responses[status]["content"]).contains_key(
                "application/problem+json"
            )


class BookDocument(BaseModel):
    name: str
    note: str | None = None


class BookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class BookState:
    def __init__(self, row, version):
        self.row, self.version = row, version


class Book:
    def __init__(self, id, name, note=None):
        self.id, self.name, self.note = id, name, note


class BookStore:
    """Versioned books; records every call and raises what the test sets."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.denied: Exception | None = None
        self.books = {
            "1": Book("1", "alpha", "n"),
            "2": Book("2", "beta"),
            "3": Book("3", "gamma"),
        }
        self.versions: dict[str, int | None] = {"1": 1, "2": 1, "3": 1}

    async def get_many(self, ids):
        self.calls.append(("get_many", list(ids)))
        return {i: self.books[i] for i in ids if i in self.books}

    async def current(self, ids):
        self.calls.append(("current", list(ids)))
        return {
            i: BookState(self.books[i], self.versions[i])
            for i in ids
            if i in self.books
        }

    async def update_many(self, items):
        self.calls.append(("update_many", [(i, d.name, d.note) for i, d in items]))
        if self.denied:
            raise self.denied
        for book_id, doc in items:
            self.books[book_id].name, self.books[book_id].note = doc.name, doc.note
        return [self.books[i] for i, _ in items]


def books(*, cap=None, guard=None, **update_options):
    store = BookStore()
    app = FastApiApp(AppConfig())
    dependencies = [Depends(guard)] if guard else []

    def get_store() -> BookStore:
        return store

    app.include_router(
        batch_get_router(
            "/books",
            response_model=BookRead,
            resource_name="books",
            resource_label="Book",
            store=get_store,
            max_rows=cap,
            dependencies=dependencies,
        )
    )
    app.include_router(
        batch_update_router(
            "/books",
            model=BookDocument,
            response_model=BookRead,
            resource_name="books",
            resource_label="Book",
            store=get_store,
            max_rows=cap,
            dependencies=dependencies,
            **update_options,
        )
    )
    return TestClient(app, raise_server_exceptions=False), store, app


def book_update(client, *requests):
    return client.post("/books:batchUpdate", json={"requests": list(requests)})


def test_batch_get_returns_rows_in_request_order_repeating_duplicates():
    client, store, _ = books()
    response = client.get(
        "/books:batchGet", params=[("ids", "3"), ("ids", "1"), ("ids", "3")]
    )
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to(
        {
            "books": [
                {"id": "3", "name": "gamma"},
                {"id": "1", "name": "alpha"},
                {"id": "3", "name": "gamma"},
            ]
        }
    )


def test_batch_get_drops_empty_values_and_does_not_split_commas():
    client, store, _ = books()
    response = client.get("/books:batchGet", params=[("ids", ""), ("ids", "1,2")])
    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.json()["detail"]).is_equal_to("Book 1,2 not found")
    assert_that(store.calls).is_equal_to([("get_many", ["1,2"])])


@pytest.mark.parametrize("params", [{}, {"ids": ""}])
def test_batch_get_requires_an_id(params):
    client, store, _ = books()
    response = client.get("/books:batchGet", params=params)
    assert_that(response.status_code).is_equal_to(400)
    assert_that(response.json()["detail"]).is_equal_to(
        "A non-empty ids parameter is required."
    )
    assert_that(store.calls).is_empty()


def test_batch_get_over_the_cap_is_a_400():
    client, store, _ = books(cap=1)
    response = client.get("/books:batchGet", params=[("ids", "1"), ("ids", "2")])
    assert_that(response.status_code).is_equal_to(400)
    assert_that(response.json()["detail"]).is_equal_to(
        "The batch exceeds the limit of 1 rows."
    )


def test_batch_get_names_the_first_missing_id():
    client, _, _ = books()
    response = client.get(
        "/books:batchGet", params=[("ids", "1"), ("ids", "9"), ("ids", "8")]
    )
    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.json()["detail"]).is_equal_to("Book 9 not found")


def test_batch_update_merges_each_patch_with_integer_ids():
    client, store, _ = books()
    response = book_update(
        client,
        {"id": 2, "patch": {"name": "beta2"}, "ifMatch": 'W/"1"'},
        {"id": "1", "patch": {"note": None}},
    )
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to(
        {"books": [{"id": "2", "name": "beta2"}, {"id": "1", "name": "alpha"}]}
    )
    assert_that(store.calls[-1]).is_equal_to(
        ("update_many", [("2", "beta2", None), ("1", "alpha", None)])
    )


def test_batch_update_ignores_if_match_on_an_unversioned_row():
    client, store, _ = books()
    store.versions["1"] = None
    response = book_update(client, {"id": "1", "patch": {}, "ifMatch": "junk"})
    assert_that(response.status_code).is_equal_to(200)


def test_batch_update_require_if_match_is_a_428_with_the_pointer():
    client, store, _ = books(require_if_match=True)
    response = book_update(
        client, {"id": "1", "patch": {}, "ifMatch": "*"}, {"id": "2", "patch": {}}
    )
    assert_that(response.status_code).is_equal_to(428)
    assert_that(pointers(response)[0][0]).is_equal_to("/requests/1/ifMatch")
    assert_that([c for c, _ in store.calls]).does_not_contain("update_many")


def test_batch_update_a_stale_precondition_is_a_412_with_the_pointer():
    client, store, _ = books()
    response = book_update(
        client, {"id": "1", "patch": {}}, {"id": "2", "patch": {}, "ifMatch": 'W/"9"'}
    )
    assert_that(response.status_code).is_equal_to(412)
    assert_that(pointers(response)[0][0]).is_equal_to("/requests/1/ifMatch")


def test_batch_update_an_unknown_id_is_a_404():
    client, store, _ = books()
    response = book_update(client, {"id": "1", "patch": {}}, {"id": "99", "patch": {}})
    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.json()["detail"]).is_equal_to("Book 99 not found")


def test_batch_update_validation_failure_writes_nothing():
    client, store, _ = books()
    response = book_update(
        client,
        {"id": "1", "patch": {"name": None}},
        {"id": "2", "patch": {"name": "ok"}},
        {"id": "3", "patch": {"note": 5}},
    )
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to("One or more rows are invalid.")
    assert_that(pointers(response)).is_equal_to(
        [
            ("/requests/0/patch/name", "This field may not be null."),
            ("/requests/2/patch/note", "Input should be a valid string"),
        ]
    )
    assert_that([c for c, _ in store.calls]).does_not_contain("update_many")


def test_batch_update_renders_items_a_store_denies():
    client, store, _ = books()
    store.denied = ItemsDenied({"1": ["Locked."]}, root="requests")
    response = book_update(client, {"id": "1", "patch": {}}, {"id": "2", "patch": {}})
    assert_that(response.status_code).is_equal_to(403)
    assert_that(pointers(response)).is_equal_to([("/requests/1", "Locked.")])
    assert_that(store.books["1"].name).is_equal_to("alpha")


@pytest.mark.parametrize(
    "body",
    [{}, {"requests": []}, {"requests": "x"}, [1]],
)
def test_batch_update_step_one_matches_batch_create(body):
    client, store, _ = resource()
    create = client.post("/orders:batchCreate", json=body)
    client, store, _ = books()
    update = client.post("/books:batchUpdate", json=body)
    assert_that(update.status_code).is_equal_to(create.status_code).is_equal_to(422)
    assert_that(pointers(update)).is_equal_to(pointers(create))
    assert_that(update.json()["detail"]).is_equal_to(create.json()["detail"])
    assert_that(store.calls).is_empty()


def test_batch_update_over_the_cap_is_the_row_cap_problem():
    client, store, _ = books(cap=1)
    response = book_update(client, {"id": "1", "patch": {}}, {"id": "2", "patch": {}})
    assert_that(response.status_code).is_equal_to(422)
    assert_that(response.json()["detail"]).is_equal_to(
        "The batch exceeds the limit of 1 rows."
    )
    assert_that(response.json()).does_not_contain_key("errors")
    assert_that(store.calls).is_empty()


def test_batch_update_reports_malformed_items_and_duplicates_before_the_store():
    client, store, _ = books()
    response = book_update(client, {"patch": {}}, {"id": "1", "patch": 3})
    assert_that(pointers(response)).is_equal_to(
        [
            ("/requests/0/id", "This field is required."),
            ("/requests/1/patch", "A merge patch must be a JSON object."),
        ]
    )
    response = book_update(client, {"id": "1", "patch": {}}, {"id": 1, "patch": {}})
    assert_that(pointers(response)).is_equal_to(
        [("/requests/1/id", "Duplicate id in batch.")]
    )
    assert_that(store.calls).is_empty()


def test_the_new_routes_run_their_dependencies_first():
    client, store, _ = books(guard=deny_everything)
    responses = [
        client.get("/books:batchGet", params={"ids": "1"}),
        book_update(client, {"id": "1", "patch": {}}),
    ]
    assert_that([r.status_code for r in responses]).is_equal_to([403, 403])
    assert_that(store.calls).is_empty()


def test_openapi_describes_the_batch_get_and_update_routes():
    _, _, app = books()
    paths = app.openapi()["paths"]
    schemas = app.openapi()["components"]["schemas"]

    get = paths["/books:batchGet"]["get"]
    assert_that(get["operationId"]).is_equal_to("booksBatchGet")
    ids = next(p for p in get["parameters"] if p["name"] == "ids")
    assert_that(ids["in"]).is_equal_to("query")
    assert_that(ids["schema"]["type"]).is_equal_to("array")

    update = paths["/books:batchUpdate"]["post"]
    assert_that(update["operationId"]).is_equal_to("booksBatchUpdate")
    request = update["requestBody"]["content"]["application/json"]["schema"]
    request_schema = schemas[request["$ref"].rsplit("/")[-1]]
    item = schemas[
        request_schema["properties"]["requests"]["items"]["$ref"].rsplit("/")[-1]
    ]
    assert_that(set(item["properties"])).is_equal_to({"id", "patch", "ifMatch"})
    for operation, statuses in (
        (get, ("400", "404")),
        (update, ("403", "404", "412", "422", "428")),
    ):
        for status in statuses:
            assert_that(operation["responses"][status]["content"]).contains_key(
                "application/problem+json"
            )
