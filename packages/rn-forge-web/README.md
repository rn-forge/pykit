# rn-forge-web

Framework-agnostic HTTP/API primitives, built on `rn-forge-commons`.

These are the wire semantics an application *promises its callers* — W3C
Trace Context propagation, the error body, the precondition contract, the
pagination envelope, the idempotency contract, the readiness aggregate, the
authentication contract, the OpenAPI naming rules, and the conformance table
the framework packages are tested against.

Fourteen flat modules, all one kind of mechanism: **inbound** HTTP wire
semantics.

## Where it sits

```text
commons ──► web ──► django
              └───► fastapi
```

`rn-forge-web` depends on **`rn-forge-commons` and nothing else in the
workspace**. It never imports `rn_forge.cli` or `rn_forge.tooling` — those are
the command-line and file-owning layers, and a package that ships into an ASGI
server has no business reaching either. It never imports a web framework:
not `django`, not `fastapi`, not `starlette`, not `rest_framework`.

`.importlinter` at the repo root carries the `web-is-framework-free` and
`web-layers` contracts, and `uv run lint-imports` proves them.

## Inbound, not outbound

The tempting rule is "everything HTTP lives in `rn-forge-web`", and it is
wrong. A circuit breaker, a retry policy and a token bucket are
transport-agnostic: a worker retrying a database call, a CLI retrying a blob
upload and an LLM adapter backing off all need them, and none of them speaks
server-side HTTP. Those live in `rn_forge.commons.integration.resilience`, so
that an Azure Blob or Key Vault adapter package can depend on commons alone
rather than dragging ASGI middleware and cursor codecs into a process that
serves no requests.

The one concern that runs the other way is `problem_from_body`, which parses an
*upstream's* `application/problem+json` back into a `ProblemDetail`. It takes a
parsed mapping and a status — not a response object — precisely so no HTTP
client library is pulled in either direction.

## What stays in a framework package

Logic that both framework packages need lives here, as framework-free
functions: rendering a problem response (`render_problem`), the field-error
entry (`field_error`), reading the current trace id, parsing an
`Authorization` header, requiring an idempotency key, the liveness body and
the OpenAPI problem-response declarations. `rn-forge-django` and
`rn-forge-fastapi` keep only the code that reads their framework's native
shapes (a DRF error tree, a pydantic error list, a Starlette exception) and
writes their framework's native response.

## Installation

None of the `rn-forge-*` packages is published to PyPI. A release is a **git
tag**, and a consumer declares it as a pinned direct URL:

```toml
dependencies = [
  "rn-forge-web @ git+https://github.com/rn-forge/pykit@rn-forge-web-v0.1.0#subdirectory=packages/rn-forge-web",
]
```

`uv add rn-forge-web` will not work and is not the supported form. Inside this
workspace, `[tool.uv.sources]` overrides that URL with the local checkout; that
override is for local development only and does not survive into a built wheel.

## Dependencies and why

**`rn-forge-commons`** — `AppException` (every exception here subclasses it, so
a consumer already catching that catches these), through its `pydantic` extra.

**`pydantic`, through that extra** — `models.py` holds `WireModel`, the
camelCase base, and `ProblemDetail`, `Page[T]`, `CheckResult` and
`HealthReport` are `WireModel` subclasses. Both framework packages use them
directly: FastAPI as request and response models, Django for its OpenAPI
components and health bodies. `rn-forge-django` therefore installs pydantic
transitively.

**`rn-forge-commons[auth]`, behind this package's own `auth` extra** — and
only for `rn_forge.web.oidc`. `OidcAuthenticator` is the single implementation
that joins commons' `JwtVerifier` to the `Authenticator` contract, so the two
framework packages stop hand-writing the same verifier-to-`Principal` glue. It
sits here rather than in commons because its signature is `Credentials` in and
`Principal` out — both web types, and commons cannot depend on web.

Behind an extra, and excluded from the curated `__init__.py`, so the rest of
the package keeps the property below: install `rn-forge-web` without extras and
nothing but commons comes with it. Import `rn_forge.web.oidc` directly.

**`secure` (2.0.1), behind this package's own `security` extra** — and only
for `rn_forge.web.security`. It is framework-agnostic (no dependencies of its
own) and emits the OWASP REST Security Cheat Sheet header preset exactly, so
it is wrapped rather than hand-rolled. Behind an extra and excluded from the
curated `__init__.py` for the same reason as `auth`; import
`rn_forge.web.security` directly.

**`opentelemetry-api`, a base dependency** — and only for `rn_forge.web.tracing`.
W3C Trace Context is read through OpenTelemetry's active-span API, following
OpenTelemetry's own library guidance: a library depends on the API only,
which is a no-op until the application configures the SDK. This package never
configures a `TracerProvider` or an exporter.

**Nothing else beyond those.** The problem shape, ETag
preconditions, cursor pagination, idempotency and health aggregation are
implemented here: the maintained libraries for each either depend on a web
framework or fix a different wire shape.

## Documentation

`uv run --directory packages/rn-forge-web --group docs mkdocs build --strict`,
or the combined site from the repo root. The adoption pack under
`docs/adoption/` is the normative material: `api-conventions.md` is what an
application's specification is written against, and `model-conventions.md` is
the persistence vocabulary both ORM packages conform to.
