# E3 — Framework adapters

**Status:** done · **Implemented:** 2026-09-12 to 2026-09-22 · **Owner:** pykit

The Django and FastAPI bindings of the web contract, and the FastAPI application layer. Each package's guides describe its current API.

[Back to the work index](../../index.md)

| ID | Delivered | Source | Implemented |
| --- | --- | --- | --- |
| F3.1 | Django and DRF adapters: problem responses, pagination, idempotency, versioned models, mixins, readiness, sequences, JWKS bearer auth, messaging, Celery, schema casing and the conformance driver | Django plan Phases 0–13 | `9d8588c` |
| F3.2 | FastAPI adapters: problem handlers, OpenAPI repair, header and query dependencies, health router, auth binding and the conformance driver | FastAPI plan Phases 0–7, 6b and 6c | `3e80dbd` |
| F3.3 | FastAPI application layer: `AppConfig` and an application factory | FastAPI app-layer plan | `c769562` |
| F3.4 | `FastApiApp` replaces the factory | Reuse plan Phase 0 | `373d6bc` |

The web contract is [E2](../E2-http-contract/index.md); later standards decisions are [E4](../E4-standards-rebaseline/index.md). [ADR-0005](../../../adr/ADR-0005.md) states the shared contract each adapter implements natively. Scaffolded FastAPI and Django applications accept both adapters in [F9.8](../E9-release-readiness/F9.8-scaffolded-acceptance.md).

## Considered and rejected

- A fluent builder for `FastApiApp` (reuse Phase 0).
- FastAPI pydantic mirrors of the wire models and the correlation middleware, both removed by E4.
- Django's access-log middleware (Phase 7), removed by E4.
- A framework-independent ORM base; each stack keeps its native ORM.

Not planned, and never scheduled: WebSockets and background-task helpers (`plans/archive/fastapi-library-plan.md`, "Deferred — do not build these yet"), and utility endpoints beyond health in the application layer (`plans/archive/fastapi-app-layer-plan.md`). Each needs its own contract and a consumer.
