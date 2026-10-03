# E3 — Framework adapters

| | |
| --- | --- |
| **State** | Closed |
| **Start Date** | 2026-09-12 |
| **Closed Date** | 2026-09-22 |

The Django and FastAPI bindings of the web contract, and the FastAPI application layer. Each package's guides describe its current API.

[Back to the work index](../../index.md)

| ID | Scope | Commits | State |
| --- | --- | --- | --- |
| F3.1 | Django and DRF adapters: problem responses, pagination, idempotency, versioned models, mixins, readiness, sequences, JWKS bearer auth, messaging, Celery, schema casing and the conformance driver | `9d8588c` | Closed |
| F3.2 | FastAPI adapters: problem handlers, OpenAPI repair, header and query dependencies, health router, auth binding and the conformance driver | `3e80dbd` | Closed |
| F3.3 | FastAPI application layer: `AppConfig` and an application factory | `c769562` | Closed |
| F3.4 | `FastApiApp` replaces the factory | `373d6bc` | Closed |

The web contract is [E2](../E2-http-contract/index.md); later standards decisions are [E4](../E4-standards-rebaseline/index.md). [ADR-0005](../../../adr/ADR-0005.md) states the shared contract each adapter implements natively. Scaffolded FastAPI and Django applications accept both adapters in [F9.8](../E9-release-readiness/F9.8-scaffolded-acceptance.md).

## Considered and rejected

- A fluent builder for `FastApiApp`.
- FastAPI pydantic mirrors of the wire models and the correlation middleware, both removed by E4.
- Django's access-log middleware, removed by E4.
- A framework-independent ORM base; each stack keeps its native ORM.

Not planned, and never scheduled: WebSockets and background-task helpers, and utility endpoints beyond health in the application layer. Each needs its own contract and a consumer.
