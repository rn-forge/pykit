# Wiring an application

Promoted from `rn-forge-web`'s interim FastAPI wiring guide, which was written to
become this package. What was a page of copy-paste handler, dependency and
router code there is a handful of calls here; what is left is the wiring an
application genuinely owns.

## The wiring module

```python
from fastapi import FastAPI

from rn_forge.fastapi import (
    health_router,
    install_problem_schema,
    operation_id,
    register_problem_handlers,
)
from rn_forge.web import CorrelationIdMiddleware, ProblemType, default_registry

from myapp.errors import OrderLocked
from myapp.settings import Settings


def create_app(*, settings: Settings, checks) -> FastAPI:
    registry = default_registry(type_base=settings.problem_type_base)
    registry.register(OrderLocked, ProblemType("order-locked", 409, "Order Locked"))

    app = FastAPI(title="Orders", generate_unique_id_function=operation_id)
    app.add_middleware(CorrelationIdMiddleware)
    register_problem_handlers(app, registry=registry, realm="orders", log=settings.log)
    install_problem_schema(app, registry=registry)
    app.include_router(health_router(checks=checks, required=["db"]))
    app.include_router(orders.router, prefix="/api/v1")
    return app
```

`create_app` is the application's, not this package's. Its shape is the
convention worth copying: it takes a constructed `Settings` and its
dependencies and constructs nothing itself, so a test builds it with fakes and
the composition root is the only place that touches real infrastructure.

## The rules the wiring depends on

1. **Register domain exceptions on the registry before
   `register_problem_handlers`.** Handlers are registered per exception type,
   because Starlette re-raises anything handled by an `Exception` handler. A row
   added later still renders correctly, but as a logged, re-raised server error.
2. **Pass the same registry to `install_problem_schema`.** Its statuses are the
   problem responses the schema declares on every operation.
3. **Install `CorrelationIdMiddleware` directly.** Never wrap it in a
   `BaseHTTPMiddleware` (a ContextVar set in its spawned task does not reliably
   reach exception handlers), and never reset the ContextVar on the way out
   (Starlette's `ServerErrorMiddleware` sits outside it and needs the value).
   If infrastructure stamps a different header, pass the same `header_name` to
   the middleware and `correlation_header` to `register_problem_handlers`.
4. **Derive every model from `WireModel`.** camelCase on the wire is enforced by
   the base class, including in a hand-built
   `JSONResponse(model.model_dump(mode="json"))`.
5. **Name non-CRUD routes.** `operation_id` covers `<resource><Verb>` for CRUD;
   give an action route an explicit `operation_id=`.

## Routes

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from rn_forge.fastapi import Page, bearer_auth, page_params, require_if_match, requires
from rn_forge.web import Cursor, Principal, Requirement, check_precondition

router = APIRouter()
caller = bearer_auth(authenticator=jwt_authenticator, log=log)
reader = requires(caller, Requirement(all_scopes=frozenset({"orders:read"})))


@router.get("/orders")
async def orders_list(
    page: Annotated[tuple[int, Cursor | None], Depends(page_params(cap=100, default=20))],
    principal: Annotated[Principal, Depends(reader)],
) -> Page[OrderOut]:
    size, cursor = page                    # size already clamped; cursor already decoded
    ...


@router.patch("/orders/{order_id}")
async def orders_update(order_id: str, if_match: Annotated[str, Depends(require_if_match())]):
    order = await repo.get(order_id)
    check_precondition(if_match, current_version=order.version, entity_id=order_id, required=True)
    ...
```

`pageSize` above the cap is clamped, never rejected — do not add a
`Query(le=...)` alongside `page_params`; that is a 422 and a specification
violation.

## What an application still writes

- **The authenticator.** `bearer_auth` takes any `rn_forge.web.Authenticator` or
  `AsyncAuthenticator`: verify the token, map claims to a `Principal`, and raise
  `AuthenticationFailed` with the reason — the reason reaches `log`, never the
  body. `basic_auth` is for local development and simple internal deployments
  only.
- **The idempotency store.** Implement `rn_forge.web.AsyncIdempotencyStore`
  over the application's database. Race safety comes from a `UNIQUE (scope, key)`
  constraint with `INSERT … ON CONFLICT DO NOTHING` and a read-back, never a
  check-then-insert. `require_idempotency_key()` reads the header; the route
  calls `record_or_replay` and `complete`.
- **The checks.** Zero-argument callables, sync or async, returning a `bool` or a
  `rn_forge.web.CheckResult`. Give a slow dependency its own timeout inside the
  check: `run_checks` does not impose one.

## Conformance

`tests/test_conformance.py` in this package is the FastAPI driver for the
`rn-forge-web` conformance table: a fresh application per case, built from the
adapters above, `depends_on` issued first, and equality asserted against the
table — never against Django's output.
