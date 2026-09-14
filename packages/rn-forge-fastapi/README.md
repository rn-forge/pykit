# rn-forge-fastapi

FastAPI adapters over `rn-forge-web`.

`rn-forge-web` settles the wire — the problem body, the cursor codec, the ETag
semantics, the idempotency reuse rule, the readiness aggregate, the 401/403
boundary. This package is the FastAPI-shaped plumbing that puts those decisions
into an application: exception-handler registration, `Depends` factories, a
router factory and an OpenAPI repair. **It makes no wire decision of its own.**
Where an adapter needed one, the decision was made in `rn-forge-web` instead —
see "Changes made to rn-forge-web" below.

| Module | What it adapts |
| --- | --- |
| `problem` | `register_problem_handlers(app)` — every error the app produces, including FastAPI's own 404/405/422, as `application/problem+json` |
| `schemas` | `WireModel` (camelCase out, either spelling in) and pydantic mirrors of the web wire shapes: `ProblemDetail`, `Page[T]`, `CheckResult`, `HealthReport` |
| `openapi` | `install_problem_schema(app)` — puts `ProblemDetail` and the problem responses into the schema and pins OpenAPI 3.1.0; `operation_id` — the shared `operationId` convention |
| `dependencies` | `page_params`, `require_idempotency_key`, `require_if_match` |
| `health` | `health_router(checks=...)` — `/healthz` and `/readyz` |
| `auth` | `bearer_auth`, `basic_auth`, `requires` — `Security` dependencies over the web auth contract |

Six flat modules, all one kind of mechanism, so the package is flat (kiln D55).

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

## The namespace decision

The import path is `rn_forge.fastapi`, and the framework's is `fastapi`, one
level apart. **Kept**, rather than falling back to `rn_forge.fastapi_adapters`:

- Python 3 has no implicit relative imports, so inside `rn_forge/fastapi/`,
  `from fastapi import APIRouter` resolves to the framework. The collision only
  bites a process that puts `src/rn_forge/` itself on `sys.path`, which nothing
  in this workspace does.
- The package is named after what it adapts, the same as `rn_forge.django`.
- Three defences hold it: the framework is always imported fully qualified
  (`from fastapi import …`, never `import fastapi`); `tests/test_namespace.py`
  asserts `rn_forge.fastapi.__path__` and `fastapi.__path__` are disjoint; and
  the import-linter contracts fail loudly if the package ever resolves to the
  framework.

## Installation

None of the `rn-forge-*` packages is on PyPI. A release is a git tag, declared
as a pinned direct URL (kiln D46):

```toml
dependencies = [
  "rn-forge-fastapi @ git+https://github.com/rn-forge/pykit@rn-forge-fastapi-v0.1.0#subdirectory=packages/rn-forge-fastapi",
]
```

`uv add rn-forge-fastapi` will not work. Inside this workspace, `[tool.uv.sources]`
overrides the URL with the local checkout, for local development only.

## What this package deliberately does not ship

- **An application factory.** The shape worth sharing — a factory that takes a
  constructed `Settings` and its dependencies and builds nothing — is a
  convention, documented in the wiring guide. A shipped `create_app` is one
  every application would immediately need to escape.
- **A dependency-injection container, a settings facade, any store.** FastAPI's
  `Depends` is the DI framework; configuration arrives as function arguments;
  an `AsyncIdempotencyStore` is SQL- or Redis-backed and belongs to the
  application or the deferred `rn-forge-sqlalchemy`.
- **A middleware module.** `rn_forge.web.CorrelationIdMiddleware` is pure ASGI
  and installs with `app.add_middleware(CorrelationIdMiddleware)` with no
  adaptation at all. The one FastAPI-specific concern — Starlette's
  `ServerErrorMiddleware` sits outside user middleware, so a 500 skips the
  header stamp — is handled where the 500 is rendered, in `problem`.
- **A token verifier.** The auth binding takes any `rn_forge.web.Authenticator`;
  verifying a JWT against a JWKS is that authenticator's job.
- **Code generation.** A future `[codegen]` extra lives in
  `rn_forge.fastapi.codegen` only; its import fence is already in
  `.importlinter`.

## Dependencies and why

**`rn-forge-web`** — every module adapts one of its primitives.
`rn-forge-commons` is not declared: nothing here imports it directly, and it
arrives pinned through `rn-forge-web`.

**`fastapi`** (floor `0.141.1`, the version that resolved on 2026-09-12) — a hard
dependency, not an extra: a package of FastAPI adapters has nothing to install
conditionally. It is used as documented, not abstracted away — an application
keeps `APIRouter`, `Depends`, `Header` and `response_model` exactly as FastAPI
defines them. `pydantic` (2.13 resolved) and `starlette` arrive with it; the
`WireModel` configuration uses `validate_by_name`/`serialize_by_alias`, which
need pydantic ≥ 2.11.

**Not wrapped:** FastAPI's `HTTPBearer`/`HTTPBasic` are used with
`auto_error=False` — kept for the `securitySchemes` entry they put in the
schema, stripped of their own 401 body and non-RFC-6750 challenge.
`fastapi-problem`, `fastapi-pagination` and similar were not adopted: each
decides a wire shape, and the wire shape is `rn-forge-web`'s.

## Changes made to rn-forge-web

The guiding rule was *if an adapter needs a decision, it belongs in the web
package*. Four gaps surfaced while writing the adapters, and each was closed
there rather than worked around here:

- `ProblemRegistry.problem_for_status(status)` — a framework 404/405 carries no
  exception type. The status-to-row mapping (intellibench's `_status_mapping`)
  folds into the registry, so Django uses the same one.
- `ProblemRegistry.build(..., problem=row)` — build from that row.
- `ProblemRegistry.rows()` — a read-only view, so handlers can be registered per
  exception type and the schema can declare the statuses in use.
- `errors_from_pointer_list` drops FastAPI's leading `body` location segment and
  renders a missing field as `This field is required.`, so pydantic and DRF
  produce the identical pointer list the conformance table requires.

- `run_checks(..., timeout=)` — a per-check timeout, so a hanging check cannot
  hang `/readyz`. A check still running when it expires is reported as `fail`,
  `timed out after <n>s`; `health_router(timeout=...)` passes it through.

Two are **open** and recorded rather than decided here:

- `Page[T]` is generic, so FastAPI names its component `Page_UserOut_`, not
  `Page`. The web conventions' "identical component names" cannot hold literally
  for a generic envelope; the naming rule needs restating there.
- The `operationId` convention in `api-conventions.md` covers CRUD only. Action
  routes need an explicit `operation_id=` until the convention says otherwise.

## Documentation

`uv run --directory packages/rn-forge-fastapi --group docs mkdocs build --strict`,
or the combined site from the repo root. The wiring guide is the page an
application is written from.
