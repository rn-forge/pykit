# rn-forge-fastapi

FastAPI adapters over `rn-forge-web`.

`rn-forge-web` settles the wire — the problem body, the cursor codec, the ETag
semantics, the idempotency reuse rule, the readiness aggregate, the 401/403
boundary. This package is the FastAPI-shaped plumbing that puts those decisions
into an application: exception-handler registration, `Depends` factories, a
router factory and an OpenAPI repair. **It makes no wire decision of its own.**

| Module | What it adapts |
| --- | --- |
| `problem` | `register_problem_handlers(app)` — every error the app produces, including FastAPI's own 404/405/422, as `application/problem+json` |
| `schemas` | `WireModel` (camelCase out, either spelling in) and pydantic mirrors of the web wire shapes: `ProblemDetail`, `Page[T]`, `CheckResult`, `HealthReport` |
| `openapi` | `FastApiApp.openapi()` repairs the cached document — adds `ProblemDetail` and the problem responses it can actually produce, accuracy only; `operation_id` — the shared `operationId` convention |
| `dependencies` | `page_params`, `require_idempotency_key`, `require_if_match` |
| `health` | `health_router(checks=...)` — `/healthz` and `/readyz` |
| `auth` | `bearer_auth`, `basic_auth`, `requires` — `Security` dependencies over the web auth contract |
| `app` | `FastApiApp(config)` — a `FastAPI` subclass with the standard adapters installed |

## Where it sits

```text
commons ──► web ──► django
              └───► fastapi      (this package)
```

`rn-forge-fastapi` depends on `rn-forge-web` and FastAPI. It never imports
`rn_forge.django` — the two framework packages are independent siblings — nor
`rn_forge.cli` or `rn_forge.tooling`. `.importlinter` carries the
`fastapi-runtime-has-no-tooling` and `web-layers` contracts, and
`uv run lint-imports` proves them.

## The import path

This package is `rn_forge.fastapi`; the framework is `fastapi`. The two do not
collide: `from fastapi import APIRouter` always resolves to the framework,
unless a process puts `src/rn_forge/` itself on `sys.path`.

## Installation

None of the `rn-forge-*` packages is on PyPI. A release is a git tag, declared
as a pinned direct URL:

```toml
dependencies = [
  "rn-forge-fastapi @ git+https://github.com/rn-forge/pykit@rn-forge-fastapi-v0.1.0#subdirectory=packages/rn-forge-fastapi",
]
```

`uv add rn-forge-fastapi` will not work. Inside this workspace, `[tool.uv.sources]`
overrides the URL with the local checkout, for local development only.

## What this package deliberately does not ship

- **Settings, infrastructure, or application policy.** `FastApiApp` wires the
  standard adapters from an explicit `AppConfig`; applications still construct
  their settings, clients, authenticators, stores and product routes.
- **A dependency-injection container, a settings facade, any store.** FastAPI's
  `Depends` is the DI framework; configuration arrives as function arguments;
  an `AsyncIdempotencyStore` is SQL- or Redis-backed and belongs to the
  application.
- **A middleware module.** `rn_forge.web.CorrelationIdMiddleware` is pure ASGI
  and installs with `app.add_middleware(CorrelationIdMiddleware)` with no
  adaptation at all. The one FastAPI-specific concern — Starlette's
  `ServerErrorMiddleware` sits outside user middleware, so a 500 skips the
  header stamp — is handled where the 500 is rendered, in `problem`.
- **A token verifier.** The auth binding takes any `rn_forge.web.Authenticator`;
  verifying a JWT against a JWKS is that authenticator's job. For OIDC that
  authenticator already exists — `rn_forge.web.oidc.OidcAuthenticator`, via this
  package's `oidc` extra — and is shared with `rn-forge-django` so both stacks
  accept the same tokens. Nothing here wraps it; pass it to `bearer_auth`.

## Dependencies

**`rn-forge-web`** — every module adapts one of its primitives.
`rn-forge-commons` is not declared: nothing here imports it directly, and it
arrives pinned through `rn-forge-web`.

**`fastapi`** (`>=0.141.1`) — a hard dependency, not an extra. It is used as
documented, not abstracted away — an application
keeps `APIRouter`, `Depends`, `Header` and `response_model` exactly as FastAPI
defines them. `pydantic` (2.13 resolved) and `starlette` arrive with it; the
`WireModel` configuration uses `validate_by_name`/`serialize_by_alias`, which
need pydantic ≥ 2.11.

**Not wrapped:** FastAPI's `HTTPBearer`/`HTTPBasic` are used with
`auto_error=False` — kept for the `securitySchemes` entry they put in the
schema, stripped of their own 401 body and non-RFC-6750 challenge.

## OpenAPI across stacks

Wire behaviour and `operationId` are identical to the Django stack; the rest of
the document text is not. `Page[T]` keeps pydantic's own name, `Page_UserOut_`.

An operation outside the six CRUD verbs is a custom method, spelled
`POST /orders/{orderId}:cancel` and named `ordersCancel` (see `rn-forge-web`'s
`api-conventions.md` §9). Spelled as a plain path segment it still gets a
mechanical name and wants an explicit `operation_id=`.

`operationId` must be unique across the document. drf-spectacular warns and
appends a numeral on a collision; FastAPI does neither, so two routes ending in
the same literal segment collide silently here.

## Documentation

`uv run --directory packages/rn-forge-fastapi --group docs mkdocs build --strict`,
or the combined site from the repo root. The wiring guide is the page an
application is written from.
