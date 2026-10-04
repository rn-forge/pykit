"""The FastAPI conformance driver: every case in `rn_forge.web.conformance.CASES`.

The fixture application is wired from this package's adapters and nothing
hand-written: if a case needs more than a line or two over them, the adapter is
missing. Assertions are against the table, never against Django's output — two
stacks agreeing on the wrong thing is not conformance.

No case is skipped in this file, and there must never be one. A case
this stack cannot satisfy is a finding: either an adapter is missing here, or
the case encodes a decision FastAPI cannot honour and belongs in the web plan.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ConfigDict, Field, field_validator

from rn_forge.fastapi import (
    AppConfig,
    CorsPolicy,
    FastApiApp,
    bearer_auth,
    conditional_get,
    deprecated,
    health_router,
    merge_into,
    merge_patch_body,
    merge_patch_openapi,
    order_by_param,
    page_params,
    require_if_match,
    requires,
)
from rn_forge.fastapi.transfer import (
    batch_create_router,
    batch_delete_router,
    import_router,
    import_template_router,
    problem_response,
    tabular_export,
    tabular_format,
)
from rn_forge.web import (
    Operation,
    ProblemDetail,
    API_CATALOG_PATH,
    check_cursor_order,
    format_order_by,
    TabularFormat,
    ImportCounts,
    ItemsDenied,
    Page,
    WireModel,
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    InMemoryAsyncIdempotencyStore,
    Principal,
    Requirement,
    ServiceUnavailable,
    TooManyRequests,
    check_precondition,
    encode_cursor,
    run_idempotent_async,
)
from rn_forge.web.conformance import CASES, VARIABLE_MEMBERS, case_by_id, redact

pytestmark = pytest.mark.unit

ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION = 7
DEPRECATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET = datetime(2026, 7, 1, tzinfo=UTC)
DEPRECATION_LINK = "https://example.com/deprecated"
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
CASING_EXEMPT = {"service-desc", "service-doc"} | set(VARIABLE_MEMBERS)


class AnyToken:
    """Verifies every token as a principal with no scopes."""

    def authenticate(self, *, credentials):
        return Principal(subject="u1")


class Charge(WireModel):
    amount: int


class Named(WireModel):
    name: str


class Stamped(WireModel):
    id: str
    create_time: datetime


class Document(WireModel):
    name: str
    note: str | None = None
    tags: list[str] = []
    settings: dict[str, Any] = {}


class OrderRow(WireModel):
    id: str
    name: str


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


class OrderCreate(WireModel):
    name: str


@dataclass
class Order:
    id: str
    name: str
    quantity: int = 0


class OrderStore:
    """One in-memory store behind every transfer route of the fixture."""

    def __init__(self) -> None:
        self.rows_by_id = {"1": Order("1", "widget")}

    async def import_rows(self, rows, *, validate_only):
        created = sum(row.id not in self.rows_by_id for row in rows)
        if not validate_only:
            for row in rows:
                self.rows_by_id[row.id] = Order(row.id, row.name, row.quantity)
        return ImportCounts(created, len(rows) - created, 0)

    async def rows(self):
        return list(self.rows_by_id.values())

    async def create_many(self, items):
        denied = {
            str(index): ["You may not create this order."]
            for index, item in enumerate(items)
            if item.name == "forbidden"
        }
        if denied:
            raise ItemsDenied(denied, root="requests")
        created = []
        for item in items:
            order = Order(str(len(self.rows_by_id) + 1), item.name)
            self.rows_by_id[order.id] = order
            created.append(order)
        return created

    async def find(self, ids):
        return [i for i in ids if i in self.rows_by_id]

    async def delete_many(self, ids):
        for order_id in ids:
            del self.rows_by_id[order_id]


EXPORT_CAP = 1


def build_app(*, failing: str | None) -> FastAPI:
    """A fresh application: the idempotency store must not carry over between cases."""

    def check(name):
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    checks = {"db": check("db"), "queue": check("queue")}
    app = FastApiApp(
        AppConfig(
            checks=checks,
            required_checks=("db",),
            realm="conformance",
            max_body_bytes=200,
            cors=CorsPolicy(allow_origins=("https://example.com",)),
        )
    )
    store = InMemoryAsyncIdempotencyStore()
    private = requires(
        bearer_auth(authenticator=AnyToken()),
        Requirement(all_scopes=frozenset({"read"})),
    )
    app.include_router(
        health_router(
            checks=checks,
            required=["db"],
            prefix="/conformance",
        )
    )

    @app.get("/conformance/boom")
    async def boom():
        raise RuntimeError("connection to db-primary.internal failed: password=hunter2")

    @app.get("/conformance/conflict")
    async def conflict():
        raise DomainConflict("Order already dispatched")

    @app.post("/conformance/validate")
    async def validate(body: Named):
        return {"name": body.name}

    @app.patch("/conformance/items/{pk}")
    async def patch_item(pk: str, if_match: str = Depends(require_if_match())):
        check_precondition(
            if_match, current_version=ITEM_VERSION, entity_id=pk, required=True
        )
        etag = EntityVersionETagCodec().format(entity_id=pk, version=ITEM_VERSION)
        return JSONResponse({"id": pk, "version": ITEM_VERSION}, headers={"ETag": etag})

    @app.get("/conformance/items/1")
    async def get_item(request: Request):
        etag = EntityVersionETagCodec().format(entity_id="1", version=ITEM_VERSION)
        not_modified = conditional_get(request, etag)
        if not_modified is not None:
            return not_modified
        return JSONResponse(
            {"id": "1", "version": ITEM_VERSION}, headers={"ETag": etag}
        )

    document: dict[str, Any] = {
        "name": "widget",
        "note": "fragile",
        "tags": ["a", "b"],
        "settings": {"color": "red", "size": "L"},
    }
    document_version = [1]
    codec = EntityVersionETagCodec()

    def document_response():
        return JSONResponse(
            {"id": "1", **document},
            headers={"ETag": codec.format(entity_id="1", version=document_version[0])},
        )

    @app.get("/conformance/documents/1")
    async def get_document():
        return document_response()

    @app.patch("/conformance/documents/1", openapi_extra=merge_patch_openapi())
    async def patch_document(
        body: bytes = Depends(merge_patch_body()),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ):
        check_precondition(
            if_match, current_version=document_version[0], entity_id="1", codec=codec
        )
        document.update(merge_into(Document, document, body).model_dump(by_alias=True))
        document_version[0] += 1
        return document_response()

    @app.get("/conformance/items")
    async def list_items(
        params=Depends(page_params(cap=2, default=2)),
        order=Depends(order_by_param(allowed=["id"])),
    ) -> Page[dict[str, str]]:
        size, cursor = params
        if cursor:
            check_cursor_order(cursor, order)
        rows = ROWS[::-1] if order and order[0].descending else ROWS
        start = (
            next(i + 1 for i, row in enumerate(rows) if row["id"] == cursor.entity_id)
            if cursor
            else 0
        )
        window = rows[start : start + size]
        more = start + size < len(rows)
        token = (
            encode_cursor(
                (window[-1]["id"],) if order else (),
                window[-1]["id"],
                format_order_by(order),
            )
            if more
            else None
        )
        return Page[dict[str, str]](items=window, next_page_token=token)

    @app.post("/conformance/charges", status_code=201)
    async def create_charge(request: Request, body: Charge):
        async def execute():
            return 201, {"charged": body.amount}

        result = await run_idempotent_async(
            store,
            scope="charges",
            key=request.headers.get("Idempotency-Key"),
            method="POST",
            body=body.model_dump(),
            execute=execute,
        )
        return JSONResponse(
            {**result.body, "replayed": result.replayed}, status_code=result.status
        )

    @app.get("/conformance/private")
    async def private_route(principal: Principal = Depends(private)):
        return {"subject": principal.subject}

    @app.get("/conformance/echo")
    async def echo():
        return {}

    @app.get(
        "/conformance/legacy",
        deprecated=True,
        dependencies=[
            Depends(
                deprecated(
                    deprecated_at=DEPRECATED_AT, sunset=SUNSET, link=DEPRECATION_LINK
                )
            )
        ],
    )
    async def legacy():
        return {"legacy": True}

    @app.get("/conformance/throttled")
    async def throttled_route():
        raise TooManyRequests("Too many requests", retry_after=30)

    @app.get("/conformance/unavailable")
    async def unavailable_route():
        raise ServiceUnavailable("Service unavailable", retry_after=5)

    orders = OrderStore()
    tabular = Depends(tabular_format())

    async def export(request: Request, fmt: TabularFormat | None, filename: str, rows):
        if fmt is None:
            return {"items": [{"id": r.id, "name": r.name} for r in rows]}
        return await tabular_export(
            rows,
            OrderRow,
            fmt,
            filename,
            max_rows=EXPORT_CAP,
            instance=request.url.path,
        )

    @app.get("/conformance/orders")
    async def export_orders(request: Request, fmt: TabularFormat | None = tabular):
        return await export(
            request, fmt, "orders.csv", list(orders.rows_by_id.values())
        )

    @app.get("/conformance/orders/named")
    async def export_named(request: Request, fmt: TabularFormat | None = tabular):
        return await export(
            request, fmt, "Ordérs 2026.csv", list(orders.rows_by_id.values())
        )

    @app.get("/conformance/orders/over-cap")
    async def export_over_cap(request: Request, fmt: TabularFormat | None = tabular):
        rows = list(orders.rows_by_id.values())
        return await export(request, fmt, "orders.csv", [*rows, *rows])

    @app.get("/conformance/orders/count")
    async def count_orders():
        return {"count": len(orders.rows_by_id)}

    @app.get("/conformance/orders/1")
    async def get_order():
        first = orders.rows_by_id["1"]
        return {"id": first.id, "name": first.name}

    @app.get("/conformance/stamped")
    async def stamped() -> Stamped:
        return Stamped(id="1", create_time=datetime(2026, 9, 23, 14, 5, tzinfo=UTC))

    @app.post("/conformance/exports")
    async def start_export():
        return JSONResponse(
            Operation(name="operations/1").as_body(),
            status_code=202,
            headers={"Location": "/conformance/operations/1"},
        )

    @app.get("/conformance/operations/1")
    async def operation_done():
        return Operation(name="operations/1", done=True, response={"id": "1"}).as_body()

    @app.get("/conformance/operations/2")
    async def operation_failed(request: Request):
        problem = ProblemDetail(
            type="about:blank",
            title="Conflict",
            status=409,
            detail="Order already dispatched",
            instance=request.url.path,
        )
        return Operation(name="operations/2", done=True, error=problem).as_body()

    def order_store() -> OrderStore:
        return orders

    for collection, cap in (("/conformance/orders", None), ("/conformance/capped", 1)):
        app.include_router(
            import_router(
                collection, model=OrderImport, store=order_store, max_rows=cap
            )
        )
        app.include_router(
            batch_create_router(
                collection,
                model=OrderCreate,
                response_model=OrderRow,
                resource_name="orders",
                store=order_store,
                max_rows=cap,
            )
        )
    app.include_router(
        import_template_router(
            "/conformance/orders", model=OrderImport, source=order_store
        )
    )
    app.include_router(
        batch_delete_router(
            "/conformance/orders", resource_label="Order", store=order_store
        )
    )

    return app


def issue(client, case):
    spec = case.request
    headers = dict(spec.headers)
    if headers.get("Content-Type") == "multipart/form-data":
        del headers["Content-Type"]
        if not spec.body:
            headers["Content-Type"] = "multipart/form-data; boundary=empty"
            return client.request(
                spec.method,
                spec.path,
                headers=headers,
                params=dict(spec.query),
                content=b"--empty--\r\n",
            )
        return client.request(
            spec.method,
            spec.path,
            headers=headers,
            params=dict(spec.query),
            files={
                name: (name, value, "text/csv") for name, value in spec.body.items()
            },
        )
    return client.request(
        spec.method,
        spec.path,
        headers=headers,
        params=dict(spec.query),
        content=None if spec.body is None else json.dumps(spec.body),
    )


def casing_violations(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key not in CASING_EXEMPT and not CAMEL_CASE.match(key):
                found.append(key)
            casing_violations(value, found)
    elif isinstance(node, list):
        for item in node:
            casing_violations(item, found)
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_fastapi_conforms(case):
    client = TestClient(
        build_app(failing=case.request.query.get("fail")),
        raise_server_exceptions=False,
    )
    for prerequisite in case.depends_on:
        issue(client, case_by_id(prerequisite))

    response = issue(client, case)

    assert_that(response.status_code).described_as("status").is_equal_to(
        case.expect_status
    )
    for name, value in case.expect_headers.items():
        assert_that(response.headers.get(name)).described_as(name).is_equal_to(value)
    for name in case.expect_absent_headers:
        assert_that(name in response.headers).described_as(name).is_false()
    for name, pattern in case.expect_header_patterns.items():
        value = response.headers.get(name)
        assert_that(value).described_as(name).is_not_none()
        assert_that(re.fullmatch(pattern, value)).described_as(
            f"{name}={value!r} ~ {pattern!r}"
        ).is_not_none()
    if case.expect_text is not None:
        assert_that(response.text).is_equal_to(case.expect_text)
        return
    body = response.json() if response.content else {}
    assert_that(redact(body)).is_equal_to(dict(case.expect_body))
    assert_that(casing_violations(body)).described_as("camelCase").is_empty()


@pytest.mark.filterwarnings("ignore:Duplicate Operation ID:UserWarning")
def test_the_fixture_serves_every_path_the_table_uses():
    """A case added for an endpoint this driver does not serve must fail here.

    The fixture mounts `health_router` twice — once via `FastApiApp`'s standard
    `/healthz`/`/readyz`, once prefixed for the CASES table — so both share an
    operationId derived from their last path segment; expected, not a wiring bug.

    The api-catalog path is added by hand: it is deliberately
    `include_in_schema=False`, so it never appears in the OpenAPI document.
    """
    paths = build_app(failing=None).openapi()["paths"]
    served = {path.replace("{pk}", "1") for path in paths} | {API_CATALOG_PATH}
    used = {case.request.path for case in CASES}
    assert_that(used - served - {"/conformance/missing"}).is_empty()
