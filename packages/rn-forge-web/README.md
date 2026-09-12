# rn-forge-web

Framework-agnostic HTTP/API primitives, built on `rn-forge-commons`.

These are the wire semantics an application *promises its callers* — the
correlation ID, the error body, the precondition contract, the pagination
envelope, the idempotency contract, the readiness aggregate, the ASGI
correlation middleware, the authentication contract, and the conformance table
the framework packages are tested against.

Nine modules, all one kind of mechanism — **inbound** HTTP wire semantics — so
the package is deliberately flat rather than grouped into sub-packages the way
`rn-forge-commons` is (kiln D55). The curated `__init__.py` is what would make
a later regrouping cheap.

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

That is not a matter of discipline. `.importlinter` at the repo root carries
the `web-is-framework-free` and `web-layers` contracts, `uv run lint-imports`
proves them, and CI gates every other job on it.

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

## Installation

None of the `rn-forge-*` packages is published to PyPI. A release is a **git
tag**, and a consumer declares it as a pinned direct URL (kiln D46):

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
a consumer already catching that catches these) and `DataclassMixin` (the wire
shapes are frozen dataclasses and serialize through it).

**Nothing else.** That is a result, not a policy: the workspace principle is
*depend on a proven library rather than reimplement it*, and this package was
planned around two candidates. Both were evaluated on 2026-09-11 and both were
rejected.

### `asgi-correlation-id` 5.0.1 — rejected

Evaluated for the correlation ContextVar and the ASGI middleware
(`context.py`, `asgi.py`).

| Criterion | Outcome |
| --- | --- |
| Pure-ASGI middleware, not `BaseHTTPMiddleware` | pass |
| ContextVar readable from a plain sync function | pass |
| Header name, generator and validator configurable | pass |
| Transitive dependency set is `starlette`-free | **fail** |

`asgi-correlation-id` 5.0.1 declares `starlette>=0.18` as a **hard runtime
dependency**, not an extra. Adopting it would make every Django/WSGI consumer
install Starlette in order to read a ContextVar — which is precisely the
boundary rule this package exists to hold, so the failure is disqualifying
regardless of how good the rest of it is. The middleware is therefore
hand-written; it is about sixty lines, and the six ASGI type aliases it needs
are declared locally for the same reason.

Revisit if the library ever moves Starlette behind an extra.

### `rfc9457` 0.4.1 — rejected

Evaluated for the RFC 9457 problem shape (`problem.py`).

| Criterion | Outcome |
| --- | --- |
| No framework dependency | pass (only `multidict`) |
| Composes with `AppException` | **fail** |
| Extension members flatten at the top level | pass |
| Ships `py.typed` | pass (though its public signatures use untyped `**kwargs`) |

Its `Problem` is an `Exception` subclass carrying its own `__init__`, `__str__`
and `__repr__`. Multiply inheriting it alongside `AppException` gives two
incompatible constructors and two string representations, and one of the two
contracts has to lose. Two further gaps make the wrapper larger than the
implementation: it models no `instance` member at all (an RFC 9457 core
member), and it has no parse direction, so `problem_from_body` would be
hand-written anyway.

Separately, it conflates the exception with the wire shape. This package keeps
them apart on purpose — `ProblemDetail` is a frozen dataclass, and
`ProblemRegistry` maps *any* exception class to a problem row by walking its
MRO — which is the part no library provides and the part that makes an adapter
subclass resolve to its base's row without anyone remembering to register it.

### The negative results — searched 2026-09-11, nothing found

For four concerns the search found no maintained, framework-agnostic library,
so hand-rolling them is the exception the workspace principle allows rather
than the default. Recorded with the date so the next person does not redo the
search, and so that if something appears later the decision is visibly
revisitable:

- **ETag / `If-Match` preconditions** (`concurrency.py`) — what exists is
  bound to Flask, Django or DRF.
- **Opaque cursor pagination** (`pagination.py`) — every candidate is an ORM
  or framework plugin, which is the layer *below* the wire spelling this
  module fixes.
- **Idempotency-key stores** (`idempotency.py`) — the maintained options are
  framework middleware, and the part worth sharing is the protocol, not an
  adapter.
- **Health-check aggregation** (`health.py`) — likewise: the libraries ship
  endpoints, and the endpoints are exactly what belongs in the framework
  packages rather than here.

## Documentation

`uv run --directory packages/rn-forge-web --group docs mkdocs build --strict`,
or the combined site from the repo root. The adoption pack under
`docs/adoption/` is the normative material: `api-conventions.md` is what an
application's specification is written against, and `model-conventions.md` is
the persistence vocabulary both ORM packages conform to.
