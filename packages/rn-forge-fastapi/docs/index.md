# rn-forge-fastapi

`rn-forge-fastapi` wires `rn-forge-web` into FastAPI. The web package settles
what goes on the wire; this package is the FastAPI-shaped plumbing that puts it
there, so every FastAPI application built on the kit spells the same six
adapters the same way.

It provides:

- **`problem`** — `register_problem_handlers`: every error, including FastAPI's
  own 404, 405 and 422, rendered as an RFC 9457 `application/problem+json` body
- **`openapi`** — the problem-response repair `FastApiApp.openapi()` applies,
  so the document declares the error responses the app sends, and
  `operation_id`, the shared `operationId` convention
- **`dependencies`** — `page_params`, `require_idempotency_key` and
  `require_if_match`
- **`health`** — `health_router`, serving `/healthz` and `/readyz`
- **`auth`** — `bearer_auth`, `basic_auth` and `requires`, producing the web
  package's `Principal`

## Where it sits

```text
commons ──► web ──► django
              └───► fastapi
```

It depends on `rn-forge-web` and FastAPI, and never imports `rn_forge.django`,
`rn_forge.cli` or `rn_forge.tooling`. `uv run lint-imports` proves it.

**Adapt, do not re-decide.** A status code, a header name or an encoding decided
here would be a divergence from the Django stack by definition, so there are
none. This package's test suite runs the `rn-forge-web` conformance table
through a FastAPI application built from these adapters, with no skips.

## Where to start

- **Wiring an application?** [Wiring an application](guides/wiring.md) is about
  a page, and it is meant to be.
- **Just want the code?** [Quickstart](guides/quickstart.md).
