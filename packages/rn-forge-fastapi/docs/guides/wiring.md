# Wiring an application

Promoted from `rn-forge-web`'s interim FastAPI wiring guide, which was written to
become this package. What was a page of copy-paste handler, dependency and
router code there is a handful of calls here; what is left is the wiring an
application genuinely owns.

## The wiring module

```python
from fastapi import APIRouter, FastAPI

from rn_forge.fastapi import (
    AppConfig,
    FastApiApp,
)
from rn_forge.web import ProblemType, default_registry

from myapp.errors import OrderLocked
from myapp.settings import Settings


def build_app(*, settings: Settings, checks) -> FastAPI:
    registry = default_registry(type_base=settings.problem_type_base)
    registry.register(OrderLocked, ProblemType("order-locked", 409, "Order Locked"))

    return FastApiApp(
        AppConfig(
            registry=registry,
            checks=checks,
            required_checks=("db",),
            realm="orders",
            log=settings.log,
        ),
        routers=(orders.router,),
        title="Orders",
    )
```

`FastApiApp` installs the common adapters only. The application's composition
root constructs `Settings`, checks, routers and infrastructure explicitly, so
tests can pass fakes and the factory never reads the environment or starts a
resource.

## The rules the wiring depends on

1. **Register domain exceptions on the registry before creating `AppConfig`.** Handlers are registered per exception type,
   because Starlette re-raises anything handled by an `Exception` handler. A row
   added later still renders correctly, but as a logged, re-raised server error.
2. **Pass that registry to `AppConfig`.** Its statuses are the problem responses
   the schema declares on every operation.
3. **Tracing.** `FastApiApp` instruments itself with
   `FastAPIInstrumentor.instrument_app` by default (`AppConfig.tracing`), after
   the kit's own middleware, so the instrumentation wraps the whole stack
   regardless of add order. It also sets a `TraceResponsePropagator` as the
   global response propagator, but only when nothing else has — an
   application that configures its own response propagator first is left
   alone. Configure a `TracerProvider` and exporter in the application, or run
   under `opentelemetry-instrument`; `FastApiApp` never does either.
4. **Derive every model from `rn_forge.web.WireModel`.** camelCase on the wire is enforced by
   the base class, including in a hand-built
   `JSONResponse(model.model_dump(mode="json"))`.
5. **Spell a non-CRUD route as a custom method.** `POST /orders/{order_id}:cancel`
   is named `ordersCancel` automatically, on both stacks. The same action as a
   plain path segment (`/orders/{order_id}/cancel`) is indistinguishable from a
   sub-collection and needs an explicit `operation_id=`.

## Routes

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from rn_forge.fastapi import bearer_auth, page_params, require_if_match, requires
from rn_forge.web import Cursor, Page, Principal, Requirement, check_precondition

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

`Page[OrderOut]` reaches the schema as pydantic's own name, `Page_OrderOut_` —
document text is not held identical across stacks (only wire behaviour and
`operationId` are; see `api-conventions.md` §9). The DRF binding names its own
paginated component its own way too, `PaginatedOrderOutList`.

`pageSize` above the cap is clamped, never rejected — do not add a
`Query(le=...)` alongside `page_params`; that is a 422 and a specification
violation.

## Security headers

`FastApiApp` installs the OWASP REST Security Cheat Sheet response headers by
default (`AppConfig.security_headers`). `Strict-Transport-Security` is
excluded from the default preset and is opt-in — `AppConfig(hsts=True)` — for
a deployment that terminates TLS itself rather than behind a front end that
already sets it.

## Service discovery

`FastApiApp` serves RFC 9727's `/.well-known/api-catalog` by default
(`AppConfig.api_catalog`), pointing at the OpenAPI document (`openapi_url`)
and docs UI (`docs_url`) it already serves, plus readiness. Set
`AppConfig(api_catalog=False)` to turn it off.

## CORS

Opt-in, and the application owns the policy:

```python
from rn_forge.fastapi import AppConfig, CorsPolicy

config = AppConfig(cors=CorsPolicy(allow_origins=("https://app.example.com",)))
```

`CorsPolicy.expose_headers` defaults to `rn_forge.web.EXPOSED_HEADERS` — the
response headers this kit emits that a browser cannot read unless a CORS
policy names them (`ETag`, `Link`, and so on). `traceresponse` needs no entry
here — the OpenTelemetry response propagator exposes it itself.
`allow_origins` has no default; naming them is the application's decision.
`CorsPolicy(allow_credentials=True, allow_origins=("*",))` raises — browsers
reject that combination.

## Deprecating a route

```python
from datetime import UTC, datetime

from rn_forge.fastapi import deprecated

SUNSET_ANNOUNCED = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET_DATE = datetime(2026, 7, 1, tzinfo=UTC)


@router.get(
    "/orders/legacy-summary",
    deprecated=True,  # marks the OpenAPI operation
    dependencies=[
        Depends(deprecated(deprecated_at=SUNSET_ANNOUNCED, sunset=SUNSET_DATE))
    ],
)
async def orders_legacy_summary(): ...
```

`deprecated=True` and the `deprecated(...)` dependency are both needed: one
marks the document, the other stamps the `Deprecation`/`Sunset`/`Link`
headers on the wire (RFC 9745, RFC 8594).

## Publishing a model no route references

A generated client sometimes needs a shape that never appears as a request or
response body — a webhook payload, an event published to a queue. Override
`openapi()` on a `FastApiApp` subclass and call `super().openapi()` first, the
same composition `FastApiApp` itself uses to repair the document:

```python
from pydantic.json_schema import models_json_schema


class MyApp(FastApiApp):
    def openapi(self):
        schema = super().openapi()
        _, definitions = models_json_schema(
            [(OrderShippedEvent, "serialization")],
            ref_template="#/components/schemas/{model}",
        )
        schema["components"]["schemas"].update(definitions.get("$defs", {}))
        return schema
```

## What an application still writes

- **The authenticator — unless it is OIDC.** For bearer tokens from an identity
  provider, install `rn-forge-fastapi[oidc]` and use the shared implementation
  rather than writing one:

  ```python
  from rn_forge.web.oidc import OidcAuthenticator

  authenticator = OidcAuthenticator.from_issuer(
      "https://idp.example.com/tenant", audience="api://orders"
  )
  caller = bearer_auth(authenticator=authenticator, log=log)
  ```

  Pass `caller` to `requires(caller, Requirement(all_scopes=...))`, then use the
  returned dependency on protected routes. `FastApiApp` registers the problem
  handlers that render authentication failures as 401 with a challenge and
  authorization failures as 403 without one.

  Build it once at startup — it holds the JWKS cache. It is the same
  authenticator `rn-forge-django` uses, so both stacks accept the same tokens.
  For any other scheme, `bearer_auth` takes any `rn_forge.web.Authenticator` or
  `AsyncAuthenticator`: verify the token, map claims to a `Principal`, and raise
  `AuthenticationFailed` with the reason — the reason reaches `log`, never the
  body. A sync `Authenticator` runs in the threadpool, so a blocking JWKS fetch
  does not stall the event loop. `basic_auth` is for local development and
  simple internal deployments only.
- **The idempotency store.** Implement `rn_forge.web.AsyncIdempotencyStore`
  over the application's database. Race safety comes from a `UNIQUE (scope, key)`
  constraint with `INSERT … ON CONFLICT DO NOTHING` and a read-back, never a
  check-then-insert. Decorate the route with `idempotent(store, scope=...)`
  (`rn_forge.fastapi.idempotent`), which wraps
  `rn_forge.web.run_idempotent_async`: the decorated route takes
  `request: Request` and returns a `Response`.

  ```python
  from fastapi import Request
  from fastapi.responses import JSONResponse
  from rn_forge.fastapi import idempotent

  @router.post("/charges", status_code=201)
  @idempotent(store, scope="charges")
  async def create_charge(request: Request, body: ChargeIn) -> JSONResponse:
      ...
  ```

- **The checks.** Zero-argument callables, sync or async, returning a `bool` or a
  `rn_forge.web.CheckResult`. Pass `health_router(timeout=...)` so a hung
  dependency is reported as `fail` rather than hanging `/readyz`; the default,
  `None`, waits indefinitely.

## Conformance

`tests/test_conformance.py` in this package is the FastAPI driver for the
`rn-forge-web` conformance table: a fresh application per case, built from the
adapters above, `depends_on` issued first, and equality asserted against the
table — never against Django's output.

## Deploying it

`rn-forge-web`'s "Deployment" guide maps `/livez`, `/readyz`, the security
headers' `hsts` flag, CORS and body-size limits onto Kubernetes, App Engine
and Azure App Service.
