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
    AUTH_FAILED_DETAIL,
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    CheckResult,
    CorrelationIdMiddleware,
    Cursor,
    DomainConflict,
    EntityVersionETagCodec,
    IdempotencyKeyRequired,
    InMemoryIdempotencyStore,
    Page,
    Principal,
    Requirement,
    ScopeAuthorizer,
    challenge_header,
    check_precondition,
    clamp_page_size,
    decode_cursor,
    default_registry,
    encode_cursor,
    errors_from_pointer_list,
    get_correlation_id,
    run_checks,
)

REGISTRY = default_registry()
CODEC = EntityVersionETagCodec()
IDEMPOTENCY = InMemoryIdempotencyStore()
AUTHORIZER = ScopeAuthorizer()
ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION, PAGE_DEFAULT, PAGE_CAP, REALM = 7, 2, 2, "conformance"

app = FastAPI()

# --- 1. correlation: pure ASGI. Never wrap this in a BaseHTTPMiddleware. ---

app.add_middleware(CorrelationIdMiddleware)


# --- 2. errors: three handlers, because three things produce an error ------


def _respond(request: Request, exc: BaseException, **extensions: Any) -> JSONResponse:
    row = REGISTRY.problem_for(exc)
    problem = REGISTRY.build(
        exc,
        instance=request.url.path,
        # A 401 says only that authentication failed; the reason goes to the log.
        detail=AUTH_FAILED_DETAIL if row.status == 401 else None,
        extensions={"correlation_id": get_correlation_id(), **extensions},
    )
    # 401 carries a challenge; 403 must not.
    headers = (
        {"WWW-Authenticate": challenge_header(realm=REALM)}
        if problem.status == 401
        else None
    )
    return JSONResponse(
        problem.as_body(),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _respond(request, exc, errors=errors_from_pointer_list(exc.errors()))


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
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if key is None:
        raise IdempotencyKeyRequired("Idempotency-Key is required", error_code=400)
    return key


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
