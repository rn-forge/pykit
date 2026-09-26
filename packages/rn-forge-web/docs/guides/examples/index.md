# Worked examples

Three applications serving the same ten endpoints — the fixture surface
`rn_forge.web.conformance` is written against. Copy one; do not re-imagine it
from the prose.

| File | Stack | Tested how |
| --- | --- | --- |
| [`asgi_app.py`](asgi_app.py) | None — a bare ASGI application over the primitives | **Executed** against the full conformance table by this package's own test suite |
| [`django_app.py`](django_app.py) | Django + DRF | Symbol-checked (see below) |
| [`fastapi_app.py`](fastapi_app.py) | FastAPI | Symbol-checked (see below) |

## How they are kept from rotting

`asgi_app.py` is the strong case: it is imported and run through every case in
`rn_forge.web.conformance.CASES` by `tests/test_examples.py`. If a primitive
changes shape, or a conformance case is added that the example does not serve,
that test fails.

The other two are not executed here, because `rn-forge-web` does not install
Django or FastAPI. `rn-forge-django` and `rn-forge-fastapi` each run the
conformance table against their own adapters.

What *is* enforced here: `tests/test_examples.py` parses all three files and
asserts that every name they import from `rn_forge.web` actually exists in its
public API. That catches the realistic rot — a renamed or removed symbol —
without importing a framework. It does not catch a semantic change in a
framework's own behaviour.

## The ten endpoints

| Path | What it exercises |
| --- | --- |
| `GET /conformance/boom` | an unregistered exception → 500, detail suppressed |
| `GET /conformance/conflict` | a registered `DomainConflict` → 409 |
| `GET /conformance/missing` | a routing 404 as a problem body |
| `POST /conformance/validate` | validation errors as RFC 6901 pointers |
| `PATCH /conformance/items/1` | `If-Match` preconditions: 428 / 412 / 400 / `*` |
| `GET /conformance/items` | AIP-158 pagination, clamped page size |
| `POST /conformance/charges` | idempotency keys with body hashing |
| `GET /conformance/readyz` | readiness aggregation and the 503 rule |
| `GET /conformance/private` | the 401/403 boundary and the challenge |
| `GET /conformance/echo` | tracing and CORS echo |
