# Wiring rn-forge-web into FastAPI

The whole adapter layer, and it is intentionally about a page. If it grows much
past this, the package boundary is wrong.

This will eventually ship as `rn-forge-fastapi`. Until it does, this is the
interim, and it is what that package will be authored from.

## 1. Correlation — the middleware ships here

```python
from rn_forge.web import CorrelationIdMiddleware

app.add_middleware(CorrelationIdMiddleware)
```

That is the whole wiring. Two things not to do:

- **Do not wrap it in a `BaseHTTPMiddleware`.** Starlette runs that in a spawned
  task, and a ContextVar set there is documented not to reliably propagate into
  exception handlers invoked from it. `CorrelationIdMiddleware` is pure ASGI
  precisely to avoid that gap.
- **Do not add a `finally: reset()`.** Starlette's `ServerErrorMiddleware` sits
  outside every user-added middleware, so a reset unbinds the value before the
  handler that needs it runs. Every request has its own copied context, so
  leaving it bound leaks nothing.

## 2. Errors — three handlers

FastAPI needs three, because three different things produce an error response.

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rn_forge.web import (
    PROBLEM_MEDIA_TYPE, ProblemType, default_registry,
    errors_from_pointer_list, get_correlation_id,
)

REGISTRY = default_registry()   # register your domain exceptions here, once

def _respond(request: Request, exc: BaseException, **extensions) -> JSONResponse:
    problem = REGISTRY.build(
        exc,
        instance=request.url.path,
        extensions={"correlation_id": get_correlation_id(), **extensions},
    )
    return JSONResponse(
        problem.as_body(), status_code=problem.status, media_type=PROBLEM_MEDIA_TYPE
    )

def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _respond(request, exc, errors=errors_from_pointer_list(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        # A framework-raised 404 must be a problem body, not Starlette's default.
        row = _STATUS_ROWS.get(exc.status_code)
        problem = (
            REGISTRY.build(exc, instance=request.url.path, detail=str(exc.detail))
            if row is None
            else ...
        )
        return _respond(request, exc)

    @app.exception_handler(Exception)
    async def _catch_all(request: Request, exc: Exception):
        return _respond(request, exc)     # 5xx detail is suppressed by the registry
```

Register `RequestValidationError` against a `validation-error`/422 row and
Starlette's `HTTPException` subclasses against the matching rows on `REGISTRY`,
rather than branching on `status_code` in the handler. The MRO walk then covers
their subclasses for free.

## 3. Request-level dependencies

Each of these is five lines, which is the argument for them living in the
application (or eventually in `rn-forge-fastapi`) rather than here.

```python
from typing import Annotated
from fastapi import Depends, Header, Query

from rn_forge.web import IdempotencyKeyRequired, clamp_page_size, decode_cursor

def page_params(cap: int = 100, default: int = 20):
    def dependency(
        page_size: Annotated[int | None, Query(alias="pageSize")] = None,
        page_token: Annotated[str | None, Query(alias="pageToken")] = None,
    ):
        # No `le=` on pageSize: AIP-158 clamps, and a 422 here is a violation.
        return (
            clamp_page_size(page_size, default=default, cap=cap),
            decode_cursor(page_token) if page_token else None,
        )
    return dependency

def require_if_match(if_match: Annotated[str | None, Header()] = None) -> str | None:
    return if_match     # check_precondition does the validating, in the handler

def require_idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if key is None:
        raise IdempotencyKeyRequired("Idempotency-Key is required", error_code=400)
    return key
```

**`Query(le=...)` on `pageSize` is the one thing to get right here.** It looks
like validation and it is a specification violation; the conformance table has
a case for exactly this.

## 4. Idempotency — a SQL store

The protocol's race safety comes from a uniqueness constraint, not a
check-then-insert. Against a `UNIQUE (scope, key)` constraint:

```python
async def record_or_replay(self, *, scope, key, request_body):
    digest = request_hash(request_body)
    await self._session.execute(
        insert(IdempotencyRow)
        .values(scope=scope, key=key, body_hash=digest)
        .on_conflict_do_nothing(index_elements=["scope", "key"])
    )
    row = await self._session.scalar(
        select(IdempotencyRow).where(
            IdempotencyRow.scope == scope, IdempotencyRow.key == key
        )
    )
    if row.body_hash != digest:
        raise IdempotencyKeyReuse(
            "Idempotency key {} was replayed with a different request body",
            key, error_code=409,
        )
    if row.response is None:
        return None
    return StoredResponse(status=row.status, body=row.response, replayed=True)
```

Two concurrent identical requests both reach the same row; one wins the insert,
both read it back. Implement `AsyncIdempotencyStore`, not `IdempotencyStore`.

## 5. Health — a router over the async runner

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from rn_forge.web import Check, run_checks

def health_router(checks: dict[str, Check], *, required: list[str]) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz():
        return {"status": "pass"}          # liveness touches nothing

    @router.get("/readyz")
    async def readyz():
        report = await run_checks(checks, required=required)
        return JSONResponse(report.as_body(), status_code=report.http_status)

    return router
```

`run_checks`, not `run_checks_sync` — and it runs the checks concurrently, so
five two-second timeouts cost two seconds rather than ten.

## 6. Casing and OpenAPI

- Give every response model an alias generator producing camelCase, with
  `populate_by_name=True` so Python code keeps snake_case.
- **Inject `ProblemDetail` into `components/schemas` explicitly.** The handlers
  above build error bodies by hand, so FastAPI's schema collection never sees
  them, and without this injection a generated TypeScript client has **no error
  type at all**. This is the non-obvious one.
- Pin the schema to OpenAPI **3.1.0** and follow the shared `operationId`
  convention.

## Conformance

```python
import pytest
from rn_forge.web.conformance import CASES, case_by_id, redact

def issue(client, case):
    return client.request(
        case.request.method, case.request.path,
        headers=dict(case.request.headers), params=dict(case.request.query),
        json=case.request.body,
    )

@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_conformance(client, case):          # `client` must be a FRESH app per case
    for prerequisite in case.depends_on:     # a replay only replays something
        issue(client, case_by_id(prerequisite))

    response = issue(client, case)
    assert response.status_code == case.expect_status
    for name, value in case.expect_headers.items():
        assert response.headers[name] == value
    for name in case.expect_absent_headers:
        assert name not in response.headers
    assert redact(response.json()) == dict(case.expect_body)
```

Two things this driver must get right: a **fresh application per case** (the
idempotency store must not carry over), and `depends_on` issued first.

Assert against the table, never against what Django produced.
