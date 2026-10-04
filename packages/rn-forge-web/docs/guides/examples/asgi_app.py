"""A complete application over `rn_forge.web`, on bare ASGI and nothing else.

This is the reference implementation of the conformance fixture surface, and
this package's own test suite runs every case in
`rn_forge.web.conformance.CASES` through it — so it is executable proof that
the primitives compose into the contract, and the first of the three
independent proofs the table is designed to collect.

Deliberately no framework: no routing library, no serialization library, no
dependency injection. Everything below is either `rn_forge.web` or the standard
library, which is what makes it a fair test of the package boundary. A real
application would use a framework for the parts that are tedious here — routing
and body parsing — and would keep this shape for everything else. The one
exception is `opentelemetry.instrumentation.asgi.OpenTelemetryMiddleware`,
which wraps the app below to bind the current trace — OpenTelemetry is not a
framework, and `rn_forge.web` never configures its `TracerProvider` or an
exporter.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.parser import BytesParser
from email.policy import HTTP
from typing import Any
from urllib.parse import parse_qs

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

from rn_forge.web import (
    EXPOSED_HEADERS,
    PROBLEM_MEDIA_TYPE,
    REQUIRED_FIELD_DETAIL,
    AuthenticationFailed,
    BodySizeLimitMiddleware,
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    InMemoryIdempotencyStore,
    ItemsDenied,
    NON_EMPTY_LIST_DETAIL,
    MERGE_PATCH_MEDIA_TYPE,
    NULL_FIELD_DETAIL,
    Message,
    Operation,
    Page,
    Principal,
    ProblemDetail,
    ProblemResponse,
    ProblemType,
    READ_MASK_PARAM,
    FieldTree,
    Receive,
    Requirement,
    RowError,
    Scope,
    ScopeAuthorizer,
    Send,
    ServiceUnavailable,
    TooManyRequests,
    VALIDATION_ERROR,
    UnsupportedMediaType,
    WireModel,
    batch_get_ids,
    check_cursor_order,
    check_item_precondition,
    check_precondition,
    clamp_page_size,
    format_order_by,
    merge_representation,
    require_patch_object,
    parse_order_by,
    content_disposition,
    decode_cursor,
    default_registry,
    deprecation_headers,
    encode_cursor,
    export_cap_problem,
    field_error,
    import_report_body,
    is_not_modified,
    liveness_body,
    negotiate_tabular_format,
    parse_batch_update,
    parse_flag,
    parse_read_mask,
    row_cap_problem,
    row_errors_problem,
    render_problem,
    run_checks,
    run_idempotent,
)
from rn_forge.web.openapi import LINKSET_MEDIA_TYPE, api_catalog_body
from rn_forge.web.security import SecurityHeadersMiddleware

# --- application state, all of it a fixture -------------------------------

REGISTRY = default_registry()
REGISTRY.register(
    RequestValidationError := type("RequestValidationError", (ValueError,), {}),
    ProblemType("validation-error", 422, "Validation Error"),
)


class NullField(RequestValidationError):
    """A `null` named a field that cannot hold one."""


CODEC = EntityVersionETagCodec()
IDEMPOTENCY = InMemoryIdempotencyStore()
AUTHORIZER = ScopeAuthorizer()

ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
PEOPLE: list[dict[str, Any]] = [
    {"id": "1", "team": "a", "score": 10},
    {"id": "2", "team": "b", "score": None},
    {"id": "3", "team": "a", "score": None},
    {"id": "4", "team": "b", "score": 5},
    {"id": "5", "team": "a", "score": 10},
]
ITEM_VERSION = 7
PAGE_DEFAULT, PAGE_CAP = 2, 2
REALM = "conformance"
DEPRECATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET = datetime(2026, 7, 1, tzinfo=UTC)
DEPRECATION_LINK = "https://example.com/deprecated"
ORDERS: dict[str, dict[str, str]] = {"1": {"id": "1", "name": "widget"}}
BOOKS: dict[str, dict[str, Any]] = {
    "1": {"name": "alpha", "version": 1},
    "2": {"name": "beta", "version": 1},
    "3": {"name": "gamma", "version": 1},
}
PROFILES: list[dict[str, Any]] = [
    {
        "id": "1",
        "displayName": "Ada",
        "address": {"city": "London", "postcode": "N1"},
        "phones": [{"kind": "home", "number": "1"}, {"kind": "work", "number": "2"}],
        "settings": {"theme": "dark"},
    },
    {
        "id": "2",
        "displayName": "Grace",
        "address": {"city": "Arlington", "postcode": "22201"},
        "phones": [],
        "settings": {},
    },
]
PROFILE_FIELDS: FieldTree = {
    "id": None,
    "displayName": None,
    "address": {"city": None, "postcode": None},
    "phones": {"kind": None, "number": None},
    "settings": None,  # free-form: no path goes inside it
}
EXPORT_CAP = 1
IMPORT_COLUMNS = ["id", "name", "Quantity"]
CAPPED_ROWS = 1
ORDER_QUANTITY = "0"
DOCUMENT: dict[str, Any] = {
    "version": 1,
    "body": {
        "id": "1",
        "name": "widget",
        "note": "fragile",
        "tags": ["a", "b"],
        "settings": {"color": "red", "size": "L"},
    },
}


# --- the handlers ---------------------------------------------------------


def boom(request: Request) -> Response:
    """An exception with no registry row: 500, and the detail must not leak."""
    raise RuntimeError("connection to db-primary.internal failed: password=hunter2")


def conflict(request: Request) -> Response:
    """A registered exception: 409, with the message as the detail."""
    raise DomainConflict("Order already dispatched")


def validate(request: Request) -> Response:
    """Validation errors normalized to RFC 6901 pointers."""
    body = request.json()
    if not isinstance(body, dict) or "name" not in body:
        raise RequestValidationError("Validation Error")
    return Response(200, {"name": body["name"]})


def patch_item(request: Request) -> Response:
    """`If-Match` preconditions: required, so absent is 428."""
    check_precondition(
        request.header("If-Match"),
        current_version=ITEM_VERSION,
        entity_id="1",
        required=True,
    )
    return Response(
        200,
        {"id": "1", "version": ITEM_VERSION},
        headers={"ETag": CODEC.format(entity_id="1", version=ITEM_VERSION)},
    )


def get_item(request: Request) -> Response:
    """Conditional GET: a matching `If-None-Match` short-circuits to 304."""
    etag = CODEC.format(entity_id="1", version=ITEM_VERSION)
    if is_not_modified(request.header("If-None-Match"), etag):
        return Response(304, {}, headers={"ETag": etag})
    return Response(200, {"id": "1", "version": ITEM_VERSION}, headers={"ETag": etag})


def get_document(request: Request) -> Response:
    return Response(200, DOCUMENT["body"], headers=_document_etag())


def patch_document(request: Request) -> Response:
    """RFC 7396 merge patch, in the order the contract fixes: media type,
    precondition, body shape, then validation of the merged document."""
    media_type = (request.header("Content-Type") or "").split(";")[0].strip().lower()
    if media_type != MERGE_PATCH_MEDIA_TYPE:
        raise UnsupportedMediaType()
    check_precondition(
        request.header("If-Match"),
        current_version=DOCUMENT["version"],
        entity_id="1",
    )
    patch = require_patch_object(request.json())
    merged = merge_representation(DOCUMENT["body"], patch) | {"id": "1"}
    if not isinstance(merged["name"], str):
        raise NullField("Validation Error")
    DOCUMENT.update(body=merged, version=DOCUMENT["version"] + 1)
    return Response(200, DOCUMENT["body"], headers=_document_etag())


def _document_etag() -> dict[str, str]:
    return {"ETag": CODEC.format(entity_id="1", version=DOCUMENT["version"])}


def get_profile(request: Request) -> Response:
    """`readMask` on a single resource; the ETag is the unmasked resource's."""
    mask = parse_read_mask(request.query(READ_MASK_PARAM), fields=PROFILE_FIELDS)
    profile = PROFILES[0]
    body = profile if mask is None else mask.apply(profile)
    return Response(200, body, headers={"ETag": CODEC.format(entity_id="1", version=1)})


def list_profiles(request: Request) -> Response:
    """`readMask` on a collection: each item is masked, the page members are not."""
    mask = parse_read_mask(request.query(READ_MASK_PARAM), fields=PROFILE_FIELDS)
    items = PROFILES if mask is None else [mask.apply(p) for p in PROFILES]
    return Response(200, Page(items=items, next_page_token=None).as_body())


def list_items(request: Request) -> Response:
    """AIP-158 pagination. Note what is *not* here: any rejection of pageSize."""
    raw_size = request.query("pageSize")
    size = clamp_page_size(
        int(raw_size) if raw_size and raw_size.lstrip("-").isdigit() else None,
        default=PAGE_DEFAULT,
        cap=PAGE_CAP,
    )

    order = parse_order_by(
        request.query("orderBy"), allowed=["id"]
    )  # InvalidOrderBy → 400
    rows = ROWS[::-1] if order and order[0].descending else ROWS

    start = 0
    if (token := request.query("pageToken")) is not None:
        cursor = decode_cursor(token)  # raises InvalidCursor → 400
        check_cursor_order(cursor, order)
        start = next(
            (i + 1 for i, row in enumerate(rows) if row["id"] == cursor.entity_id), 0
        )

    window = rows[start : start + size]
    has_more = start + size < len(rows)
    page = Page(
        items=window,
        next_page_token=(
            encode_cursor(
                (window[-1]["id"],) if order else (),
                window[-1]["id"],
                format_order_by(order),
            )
            if has_more
            else None
        ),
    )
    return Response(200, page.as_body())


def list_people(request: Request) -> Response:
    """Several `orderBy` terms: nulls last, the key breaking ties, one token value per term."""
    order = parse_order_by(request.query("orderBy"), allowed=["id", "team", "score"])
    keys = [(t.field, t.descending) for t in order]
    if not any(field == "id" for field, _ in keys):
        keys.append(("id", keys[-1][1] if keys else False))
    rows = list(PEOPLE)
    for field, descending in reversed(keys):  # stable passes, last term first
        present = [r for r in rows if r[field] is not None]
        present.sort(key=lambda r: r[field], reverse=descending)
        rows = present + [r for r in rows if r[field] is None]

    raw_size = request.query("pageSize")
    size = clamp_page_size(
        int(raw_size) if raw_size and raw_size.isdigit() else None,
        default=5,
        cap=5,
    )
    start = 0
    if (token := request.query("pageToken")) is not None:
        cursor = decode_cursor(token)
        check_cursor_order(cursor, order)
        start = next(i + 1 for i, r in enumerate(rows) if r["id"] == cursor.entity_id)

    window = rows[start : start + size]
    next_token = (
        encode_cursor(
            tuple(window[-1][t.field] for t in order),
            str(window[-1]["id"]),
            format_order_by(order),
        )
        if start + size < len(rows)
        else None
    )
    return Response(200, Page(items=window, next_page_token=next_token).as_body())


def create_charge(request: Request) -> Response:
    """An idempotent unsafe endpoint, over `run_idempotent`."""
    body = request.json()

    def execute() -> tuple[int, dict[str, Any]]:
        return 201, {"charged": body["amount"]}

    result = run_idempotent(
        IDEMPOTENCY,
        scope="charges",
        key=request.header("Idempotency-Key"),
        method="POST",
        body=body,
        execute=execute,
    )
    return Response(result.status, {**result.body, "replayed": result.replayed})


async def readyz(request: Request) -> Response:
    """Readiness. `db` is required, `queue` is not — hence 503 versus 200."""
    failing = request.query("fail")

    def make(name: str) -> Callable[[], CheckResult]:
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    report = await run_checks(
        {"db": make("db"), "queue": make("queue")}, required=["db"]
    )
    return Response(report.http_status, report.as_body())


def livez(request: Request) -> Response:
    """Liveness. Touches no dependency."""
    return Response(200, liveness_body())


def throttled(request: Request) -> Response:
    """RFC 6585 §4: 429 with `Retry-After`."""
    raise TooManyRequests("Too many requests", retry_after=30)


def unavailable(request: Request) -> Response:
    """RFC 9110 §15.6.4: 503 with `Retry-After`."""
    raise ServiceUnavailable("Service unavailable", retry_after=5)


def private(request: Request) -> Response:
    """The 401/403 boundary — the two failures must not look alike."""
    header = request.header("Authorization")
    if header is None or not header.startswith("Bearer "):
        raise AuthenticationFailed("No credentials were supplied")

    # A real application verifies the token here, through the commons module,
    # and never reports *why* verification failed.
    principal = Principal(subject="u1", scopes=frozenset())
    AUTHORIZER.authorize(
        principal, requires=Requirement(all_scopes=frozenset({"read"}))
    )
    return Response(200, {"subject": principal.subject})


def echo(request: Request) -> Response:
    """The tracing contract, and (when CORS-fetched) the kit's exposed headers.

    A real CORS policy is a framework binding's job (`rn_forge.fastapi.cors`,
    `rn_forge.django.cors`); this is the minimum needed to prove the contract
    on bare ASGI, not a reusable middleware.
    """
    headers: dict[str, str] = {}
    origin = request.header("Origin")
    if origin is not None:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Expose-Headers"] = ", ".join(EXPOSED_HEADERS)
    return Response(200, {}, headers=headers)


def legacy(request: Request) -> Response:
    """A deprecated endpoint: RFC 9745/RFC 8594 headers on every response."""
    return Response(
        200,
        {"legacy": True},
        headers=deprecation_headers(
            deprecated_at=DEPRECATED_AT, sunset=SUNSET, link=DEPRECATION_LINK
        ),
    )


def api_catalog(request: Request) -> Response:
    """RFC 9727's `/.well-known/api-catalog`."""
    return Response(
        200,
        api_catalog_body(
            anchor="/",
            service_desc="/openapi.json",
            service_doc="/docs",
            status="/readyz",
        ),
        media_type=LINKSET_MEDIA_TYPE,
    )


def _from_problem(rendered: ProblemResponse) -> Response:
    return Response(
        rendered.status,
        rendered.body,
        headers=dict(rendered.headers),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _field_problem(request: Request, name: str, detail: str) -> Response:
    """A 422 whose single `errors` entry points at the top-level member *name*."""
    return _from_problem(
        render_problem(
            REGISTRY,
            ValueError("Validation Error"),
            instance=request.path,
            problem=VALIDATION_ERROR,
            extensions={"errors": [field_error((name,), detail)]},
        )
    )


def _export(request: Request, filename: str, rows: list[dict[str, str]]) -> Response:
    """Export negotiation. Only CSV is written here; xlsx needs a codec."""
    fmt = negotiate_tabular_format(
        request.header("Accept"), request.query("format"), ["csv"]
    )
    if fmt is None:
        return Response(200, {"items": rows})
    if len(rows) > EXPORT_CAP:
        return _from_problem(export_cap_problem(EXPORT_CAP, instance=request.path))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["id", "name"])
    writer.writeheader()
    writer.writerows(rows)
    headers = {
        "Content-Disposition": content_disposition(f"{filename}.{fmt.extension}")
    }
    origin = request.header("Origin")
    if origin is not None:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Expose-Headers"] = ", ".join(EXPOSED_HEADERS)
    return Response(
        200,
        {},
        headers=headers,
        media_type=fmt.media_type,
        raw=out.getvalue().encode(),
    )


def export_orders(request: Request) -> Response:
    return _export(request, "orders", list(ORDERS.values()))


def export_named(request: Request) -> Response:
    return _export(request, "Ordérs 2026", list(ORDERS.values()))


def export_over_cap(request: Request) -> Response:
    return _export(request, "orders", [*ORDERS.values(), *ORDERS.values()])


def count_orders(request: Request) -> Response:
    return Response(200, {"count": len(ORDERS)})


def get_order(request: Request) -> Response:
    return Response(200, ORDERS["1"])


class Stamped(WireModel):
    id: str
    create_time: datetime


def get_stamped(request: Request) -> Response:
    """AIP-142: the model renders the instant as RFC 3339 UTC with a `Z`."""
    stamped = Stamped(id="1", create_time=datetime(2026, 9, 23, 14, 5, tzinfo=UTC))
    return Response(200, stamped.model_dump(mode="json"))


def start_export(request: Request) -> Response:
    """AIP-151: `202`, the operation in `Location`, and the operation unfinished."""
    operation = Operation(name="operations/1")
    return Response(
        202,
        operation.as_body(),
        headers={"Location": "/conformance/operations/1"},
    )


def get_operation(request: Request) -> Response:
    """A finished operation with a response, and one that failed with a problem."""
    if request.path.endswith("/2"):
        problem = ProblemDetail(
            type="about:blank",
            title="Conflict",
            status=409,
            detail="Order already dispatched",
            instance=request.path,
        )
        return Response(
            200, Operation(name="operations/2", done=True, error=problem).as_body()
        )
    operation = Operation(name="operations/1", done=True, response={"id": "1"})
    return Response(200, operation.as_body())


def _import(request: Request, cap: int | None) -> Response:
    """Multipart upload, all or nothing, honouring `validateOnly`."""
    message = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: "
        + (request.header("Content-Type") or "").encode()
        + b"\r\n\r\n"
        + request.raw
    )
    upload = next(
        (part for part in message.iter_parts() if part.get_filename() == "file"),
        None,
    )
    if upload is None:
        return _field_problem(request, "file", REQUIRED_FIELD_DETAIL)
    rows = list(csv.DictReader(io.StringIO(upload.get_content())))
    if cap is not None and len(rows) > cap:
        return _from_problem(row_cap_problem("import", cap, instance=request.path))
    errors = [
        RowError(i, "Quantity", "Enter a whole number.")
        for i, row in enumerate(rows)
        if not row["Quantity"].isdigit()
    ]
    if errors:
        return _from_problem(row_errors_problem(errors, instance=request.path))
    created = sum(row["id"] not in ORDERS for row in rows)
    validate_only = parse_flag(request.query("validateOnly"))
    if not validate_only:
        ORDERS.update(
            {row["id"]: {"id": row["id"], "name": row["name"]} for row in rows}
        )
    return Response(
        200,
        import_report_body(
            created=created,
            updated=len(rows) - created,
            skipped=0,
            validate_only=validate_only,
        ),
    )


def import_orders(request: Request) -> Response:
    return _import(request, None)


def import_capped(request: Request) -> Response:
    return _import(request, CAPPED_ROWS)


def import_template(request: Request) -> Response:
    """The import columns as a CSV header row, plus the orders when `prefill`."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(IMPORT_COLUMNS)
    if parse_flag(request.query("prefill")):
        writer.writerows(
            [order["id"], order["name"], ORDER_QUANTITY] for order in ORDERS.values()
        )
    return Response(
        200,
        {},
        headers={"Content-Disposition": content_disposition("import-template.csv")},
        media_type="text/csv",
        raw=out.getvalue().encode(),
    )


def _batch_create(request: Request, cap: int | None) -> Response:
    items = request.json()["requests"]
    if not items:
        return _field_problem(request, "requests", NON_EMPTY_LIST_DETAIL)
    if cap is not None and len(items) > cap:
        return _from_problem(row_cap_problem("batch", cap, instance=request.path))
    errors = [
        RowError(i, "name", REQUIRED_FIELD_DETAIL)
        for i, item in enumerate(items)
        if "name" not in item
    ]
    if errors:
        return _from_problem(
            row_errors_problem(errors, instance=request.path, root="requests")
        )
    denied: dict[str | int, list[str]] = {
        i: ["You may not create this order."]
        for i, item in enumerate(items)
        if item["name"] == "forbidden"
    }
    if denied:
        raise ItemsDenied(denied, root="requests")
    created: list[dict[str, str]] = []
    for item in items:
        order = {"id": str(len(ORDERS) + 1), "name": item["name"]}
        ORDERS[order["id"]] = order
        created.append(order)
    return Response(200, {"orders": created})


def batch_create_orders(request: Request) -> Response:
    return _batch_create(request, None)


def batch_create_capped(request: Request) -> Response:
    return _batch_create(request, CAPPED_ROWS)


def batch_delete_orders(request: Request) -> Response:
    ids = request.json()["ids"]
    for order_id in ids:
        if order_id not in ORDERS:
            raise LookupError(f"Order {order_id} not found")
    for order_id in ids:
        del ORDERS[order_id]
    return Response(204, {})


BOOK_FIELDS: FieldTree = {"id": None, "name": None}


def _book(book_id: str) -> dict[str, str]:
    return {"id": book_id, "name": BOOKS[book_id]["name"]}


def _batch_get_books(request: Request, cap: int | None) -> Response:
    ids = batch_get_ids(request.query_all("ids"), cap=cap)
    for book_id in ids:
        if book_id not in BOOKS:
            raise LookupError(f"Book {book_id} not found")
    mask = parse_read_mask(request.query(READ_MASK_PARAM), fields=BOOK_FIELDS)
    books = [_book(book_id) for book_id in ids]
    return Response(
        200, {"books": books if mask is None else [mask.apply(b) for b in books]}
    )


def _batch_update_books(request: Request, cap: int | None) -> Response:
    """The steps in the order the contract fixes; nothing is written before the last."""
    items = parse_batch_update(request.json(), cap=cap, instance=request.path)
    if isinstance(items, ProblemResponse):
        return _from_problem(items)
    for item in items:
        if item.id not in BOOKS:
            raise LookupError(f"Book {item.id} not found")
    for item in items:
        check_item_precondition(
            item,
            current_version=BOOKS[item.id]["version"],
            entity_id=item.id,
            codec=CODEC,
            required=False,
        )
    merged = {
        item.id: merge_representation({"name": BOOKS[item.id]["name"]}, item.patch)
        for item in items
    }
    failures = [
        field_error(
            ("requests", item.index, "patch", "name"),
            NULL_FIELD_DETAIL
            if merged[item.id]["name"] is None
            else "Not a valid string.",
        )
        for item in items
        if not isinstance(merged[item.id]["name"], str)
    ]
    if failures:
        return _from_problem(
            render_problem(
                REGISTRY,
                ValueError("Validation Error"),
                instance=request.path,
                problem=VALIDATION_ERROR,
                detail="One or more rows are invalid.",
                extensions={"errors": failures},
            )
        )
    for item in items:
        BOOKS[item.id]["name"] = merged[item.id]["name"]
        BOOKS[item.id]["version"] += 1
    return Response(200, {"books": [_book(item.id) for item in items]})


def batch_get_books(request: Request) -> Response:
    return _batch_get_books(request, None)


def batch_get_capped_books(request: Request) -> Response:
    return _batch_get_books(request, CAPPED_ROWS)


def batch_update_books(request: Request) -> Response:
    return _batch_update_books(request, None)


def batch_update_capped_books(request: Request) -> Response:
    return _batch_update_books(request, CAPPED_ROWS)


ROUTES: dict[tuple[str, str], Callable[..., Any]] = {
    ("GET", "/conformance/boom"): boom,
    ("GET", "/conformance/conflict"): conflict,
    ("POST", "/conformance/validate"): validate,
    ("PATCH", "/conformance/items/1"): patch_item,
    ("GET", "/conformance/items/1"): get_item,
    ("GET", "/conformance/documents/1"): get_document,
    ("PATCH", "/conformance/documents/1"): patch_document,
    ("GET", "/conformance/profiles"): list_profiles,
    ("GET", "/conformance/profiles/1"): get_profile,
    ("GET", "/conformance/items"): list_items,
    ("GET", "/conformance/people"): list_people,
    ("POST", "/conformance/charges"): create_charge,
    ("GET", "/conformance/readyz"): readyz,
    ("GET", "/conformance/livez"): livez,
    ("GET", "/conformance/throttled"): throttled,
    ("GET", "/conformance/unavailable"): unavailable,
    ("GET", "/conformance/private"): private,
    ("GET", "/conformance/echo"): echo,
    ("GET", "/conformance/legacy"): legacy,
    ("GET", "/.well-known/api-catalog"): api_catalog,
    ("GET", "/conformance/orders"): export_orders,
    ("GET", "/conformance/orders/named"): export_named,
    ("GET", "/conformance/orders/over-cap"): export_over_cap,
    ("GET", "/conformance/orders/count"): count_orders,
    ("GET", "/conformance/orders/1"): get_order,
    ("GET", "/conformance/stamped"): get_stamped,
    ("POST", "/conformance/exports"): start_export,
    ("GET", "/conformance/operations/1"): get_operation,
    ("GET", "/conformance/operations/2"): get_operation,
    ("POST", "/conformance/orders:import"): import_orders,
    ("GET", "/conformance/orders:importTemplate"): import_template,
    ("POST", "/conformance/capped:import"): import_capped,
    ("POST", "/conformance/capped:batchCreate"): batch_create_capped,
    ("POST", "/conformance/orders:batchCreate"): batch_create_orders,
    ("POST", "/conformance/orders:batchDelete"): batch_delete_orders,
    ("GET", "/conformance/books:batchGet"): batch_get_books,
    ("POST", "/conformance/books:batchUpdate"): batch_update_books,
    ("GET", "/conformance/capped-books:batchGet"): batch_get_capped_books,
    ("POST", "/conformance/capped-books:batchUpdate"): batch_update_capped_books,
}


# --- the plumbing ---------------------------------------------------------


class Request:
    """The three things a handler above needs off the wire."""

    def __init__(self, scope: Scope, body: bytes) -> None:
        self._scope = scope
        self._body = body
        self._query = parse_qs(scope.get("query_string", b"").decode())

    def header(self, name: str) -> str | None:
        wanted = name.lower().encode()
        return next(
            (
                v.decode()
                for k, v in self._scope.get("headers", [])
                if k.lower() == wanted
            ),
            None,
        )

    def query(self, name: str) -> str | None:
        values = self._query.get(name)
        return values[0] if values else None

    def query_all(self, name: str) -> list[str]:
        return self._query.get(name, [])

    def json(self) -> Any:
        return json.loads(self._body) if self._body else None

    @property
    def raw(self) -> bytes:
        return self._body

    @property
    def path(self) -> str:
        return self._scope.get("path", "")


class Response:
    """A status, a JSON body and any extra headers."""

    def __init__(
        self,
        status: int,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        media_type: str = "application/json",
        raw: bytes | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = dict(headers or {})
        self.media_type = media_type
        self.raw = raw


async def application(scope: Scope, receive: Receive, send: Send) -> None:
    """Route, invoke, and turn anything raised into a problem body."""
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    request = Request(scope, body)
    handler = ROUTES.get((scope.get("method", "GET"), request.path))

    try:
        if handler is None:
            raise LookupError("Not Found")
        result = handler(request)
        response = await result if hasattr(result, "__await__") else result
    except Exception as exc:  # noqa: BLE001 - every failure becomes a problem body
        response = _problem_response(exc, request)

    await _send(send, response)


def _problem_response(exc: BaseException, request: Request) -> Response:
    """The single place an exception becomes a response. There is no other."""
    return _from_problem(
        render_problem(
            REGISTRY,
            exc,
            instance=request.path,
            extensions=_error_extensions(exc),
            realm=REALM,
        )
    )


def _error_extensions(exc: BaseException) -> dict[str, Any]:
    """Field errors, when there are any."""
    if isinstance(exc, RequestValidationError):
        detail = (
            NULL_FIELD_DETAIL if isinstance(exc, NullField) else REQUIRED_FIELD_DETAIL
        )
        return {"errors": [field_error(("name",), detail)]}
    return {}


async def _send(send: Send, response: Response) -> None:
    """Serialize one response onto the ASGI send channel.

    RFC 9110 §15.4.5: a 304 carries no body, so it gets no `Content-Type`
    either; nor does a 204.
    """
    bodyless = response.status in (204, 304)
    if bodyless:
        payload = b""
    elif response.raw is not None:
        payload = response.raw
    else:
        payload = json.dumps(response.body).encode()
    headers: list[tuple[bytes, bytes]] = [
        (b"content-length", str(len(payload)).encode()),
    ]
    if not bodyless:
        headers.insert(0, (b"content-type", response.media_type.encode()))
    headers += [(k.lower().encode(), v.encode()) for k, v in response.headers.items()]
    start: Message = {
        "type": "http.response.start",
        "status": response.status,
        "headers": headers,
    }
    await send(start)
    await send({"type": "http.response.body", "body": payload})


app = OpenTelemetryMiddleware(
    SecurityHeadersMiddleware(BodySizeLimitMiddleware(application, max_bytes=200))
)
"""The application, with the current trace bound by the OTel ASGI instrumentation.
This is what a server runs."""
