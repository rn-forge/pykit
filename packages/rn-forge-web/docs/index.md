# rn-forge-web

`rn-forge-web` holds the HTTP/API primitives that are genuinely
framework-agnostic — the wire semantics an application *promises its callers*,
shared by Django/DRF, FastAPI/Starlette and anything else that speaks HTTP.

It provides:

- **`tracing`** — W3C Trace Context: reading the current OpenTelemetry span's
  trace and span ids
- **`problem`** — RFC 9457 problem details, plus an exception→problem registry
  that resolves by MRO, the 5xx detail policy, the two validation-error
  normalizers, and the parse direction for consuming an upstream's problem body
- **`exceptions`** — the conflict, precondition, cursor, idempotency and auth
  exceptions, all `AppException` subclasses
- **`concurrency`** — ETag validators and the `If-Match` precondition check,
  with 412/428 rather than a blanket 409
- **`pagination`** — opaque cursors in Google AIP-158's spelling, with the page
  size clamped and never rejected
- **`idempotency`** — the store protocol (sync and async), request hashing, and
  an in-memory double
- **`health`** — readiness-check aggregation with four statuses, and the HTTP
  status derived once rather than per framework
- **`asgi`** — the request-body size limit, pure ASGI and Starlette-free
- **`auth`** — `Principal`, the authenticator/authorizer protocols, and the
  401/403 + `WWW-Authenticate` contract
- **`conformance`** — the scenario table both framework packages are tested
  against, shipped as framework-free data

## Why this package exists

Every module here was implemented **twice, independently**, by two codebases
that never shared code — a Django/DRF application and a FastAPI one. That the
same seven concerns turned up in both is the evidence that they are real. That
the two implementations *disagreed* — on the header name, on 409 versus 412, on
whether to reset a ContextVar, on whether a page size above the cap is an error
— is why they belong in one place rather than two.

Where they disagreed, this package picks one and says why in the module's own
docstring. Those calls are the substance; the code is small.

## Where it sits

```text
commons ──► web ──► django
              └───► fastapi
```

It depends on `rn-forge-commons` and nothing else in the workspace, and it
imports no web framework, no `rn_forge.cli` and no `rn_forge.tooling`.
`uv run lint-imports` proves it, and CI gates every other job on that.

**Inbound, not outbound.** Circuit breakers, retries and rate limiting are
transport-agnostic and live in `rn-forge-commons` — a worker retrying a database
call needs them and serves no HTTP. This package is about what a server
promises its callers.

## Where to start

- **Writing an application specification?** The
  [API conventions](adoption/api-conventions.md) page is normative and is meant
  to be read on its own.
- **Wiring an existing application?** [Django](adoption/wiring-django.md) or
  [FastAPI](adoption/wiring-fastapi.md), then the
  [checklist](adoption/checklist.md).
- **Just want the code?** [Quickstart](guides/quickstart.md).
