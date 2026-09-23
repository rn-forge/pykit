"""The same ten endpoints on FastAPI.

Not executed by this package's tests — installing FastAPI here would put a web
framework in `rn-forge-web`'s dependency graph, which is the boundary the
package exists to hold. It is symbol-checked against the public API. Its
end-to-end proof is the conformance driver `rn-forge-fastapi` ships, which runs
the same ten endpoints built from that package's adapters instead of by hand.

Compare it with `asgi_app.py` and `django_app.py`: the handlers differ, and
every wire decision is made by the same call into `rn_forge.web`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from rn_forge.web import (
    IDEMPOTENCY_KEY_HEADER,
    PROBLEM_MEDIA_TYPE,
    REQUIRED_FIELD_DETAIL,
    AuthenticationFailed,
    CheckResult,
    Cursor,
    DomainConflict,
    EntityVersionETagCodec,
    InMemoryIdempotencyStore,
    Page,
    Principal,
    Requirement,
    ScopeAuthorizer,
    check_idempotency_key,
    check_precondition,
    clamp_page_size,
    decode_cursor,
    default_registry,
    encode_cursor,
    field_error,
    render_problem,
    run_checks,
)

REGISTRY = default_registry()
CODEC = EntityVersionETagCodec()
IDEMPOTENCY = InMemoryIdempotencyStore()
AUTHORIZER = ScopeAuthorizer()
ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION, PAGE_DEFAULT, PAGE_CAP, REALM = 7, 2, 2, "conformance"

app = FastAPI()

# --- 1. tracing: FastAPIInstrumentor.instrument_app(app), not a middleware. -
# `rn_forge.fastapi.FastApiApp` does this by default; a hand-assembled `FastAPI`
# calls it directly. Left out of this endpoint-only example — see
# `rn-forge-fastapi`'s own `docs/guides/wiring.md`.


# --- 2. errors: three handlers, because three things produce an error ------


def _respond(request: Request, exc: BaseException, **extensions: Any) -> JSONResponse:
    # The trace_id extension, the masked 401 detail and the challenge (never on
    # a 403) all come from render_problem.
    rendered = render_problem(
        REGISTRY, exc, instance=request.url.path, extensions=extensions, realm=REALM
    )
    return JSONResponse(
        rendered.body,
        status_code=rendered.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(rendered.headers),
    )


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        field_error(
            e["loc"][1:] if e["loc"][:1] == ("body",) else e["loc"],
            REQUIRED_FIELD_DETAIL if e["type"] == "missing" else e["msg"],
        )
        for e in exc.errors()
    ]
    return _respond(request, exc, errors=errors)


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # A framework-raised 404 is a problem body, not Starlette's default page.
    return _respond(request, exc)


@app.exception_handler(Exception)
async def _catch_all(request: Request, exc: Exception) -> JSONResponse:
    return _respond(request, exc)  # the registry suppresses the 5xx detail


# --- 3. dependencies -------------------------------------------------------


def page_params(
    page_size: Annotated[int | None, Query(alias="pageSize")] = None,
    page_token: Annotated[str | None, Query(alias="pageToken")] = None,
) -> tuple[int, Cursor | None]:
    """No `le=` on pageSize. AIP-158 clamps; a 422 here is a violation."""
    return (
        clamp_page_size(page_size, default=PAGE_DEFAULT, cap=PAGE_CAP),
        decode_cursor(page_token) if page_token else None,
    )


def require_idempotency_key(
    key: Annotated[str | None, Header(alias=IDEMPOTENCY_KEY_HEADER)] = None,
) -> str:
    return check_idempotency_key(key)


# --- 4. the endpoints ------------------------------------------------------


class ChargeRequest(BaseModel):
    amount: int


class ValidateRequest(BaseModel):
    name: str


@app.get("/conformance/boom")
async def boom() -> dict[str, Any]:
    raise RuntimeError("connection to db-primary.internal failed: password=hunter2")


@app.get("/conformance/conflict")
async def conflict() -> dict[str, Any]:
    raise DomainConflict("Order already dispatched")


@app.post("/conformance/validate")
async def validate(body: ValidateRequest) -> dict[str, Any]:
    return {"name": body.name}


@app.patch("/conformance/items/{pk}")
async def patch_item(
    pk: str, if_match: Annotated[str | None, Header(alias="If-Match")] = None
) -> JSONResponse:
    check_precondition(
        if_match, current_version=ITEM_VERSION, entity_id=pk, required=True
    )
    return JSONResponse(
        {"id": pk, "version": ITEM_VERSION},
        headers={"ETag": CODEC.format(entity_id=pk, version=ITEM_VERSION)},
    )


@app.get("/conformance/items")
async def list_items(
    params: Annotated[tuple[int, Cursor | None], Depends(page_params)],
) -> dict[str, Any]:
    size, cursor = params
    start = (
        next((i + 1 for i, r in enumerate(ROWS) if r["id"] == cursor.entity_id), 0)
        if cursor
        else 0
    )
    window = ROWS[start : start + size]
    more = start + size < len(ROWS)
    page = Page(
        items=window,
        next_page_token=encode_cursor(window[-1]["id"], window[-1]["id"])
        if more
        else None,
    )
    return page.as_body()


@app.post("/conformance/charges", status_code=201)
async def create_charge(
    body: ChargeRequest, key: Annotated[str, Depends(require_idempotency_key)]
) -> JSONResponse:
    payload = body.model_dump()
    stored = IDEMPOTENCY.record_or_replay(
        scope="charges", key=key, request_body=payload
    )
    if stored is not None:
        return JSONResponse(
            {**stored.body, "replayed": True}, status_code=stored.status
        )
    result = {"charged": body.amount}
    IDEMPOTENCY.complete(scope="charges", key=key, status=201, response_body=result)
    return JSONResponse({**result, "replayed": False}, status_code=201)


@app.get("/conformance/private")
async def private(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise AuthenticationFailed("No credentials were supplied")
    principal = Principal(subject="u1", scopes=frozenset())
    AUTHORIZER.authorize(
        principal, requires=Requirement(all_scopes=frozenset({"read"}))
    )
    return {"subject": principal.subject}


@app.get("/conformance/readyz")
async def readyz(fail: str | None = None) -> JSONResponse:
    def make(name: str):
        return lambda: CheckResult(
            status="fail" if name == fail else "pass",
            reason="unreachable" if name == fail else None,
        )

    # run_checks runs them concurrently: five 2s timeouts cost 2s, not 10s.
    report = await run_checks(
        {"db": make("db"), "queue": make("queue")}, required=["db"]
    )
    return JSONResponse(report.as_body(), status_code=report.http_status)


@app.get("/conformance/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "pass"}  # liveness touches nothing


@app.get("/conformance/echo")
async def echo() -> dict[str, Any]:
    return {}
