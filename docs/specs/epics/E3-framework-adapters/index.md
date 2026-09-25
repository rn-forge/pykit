# E3 — Framework adapters

This epic records the implemented Django and FastAPI bindings and the application layer. Each package's guides define its current API.

**Status:** done

**Owner:** pykit.

**Implemented:** `9d8588c`, `3e80dbd`, `c769562`, `373d6bc` (historical commits; no new tag implied).

[Back to the work index](../../index.md)

| Legacy feature | Result |
| --- | --- |
| Django Phases 0–13 | DRF and Django adapters, models, auth, messaging, Celery and conformance driver. |
| FastAPI Phases 0–7, 6b and 6c | FastAPI adapters, auth binding, guides and conformance driver. |
| FastAPI application layer and reuse Phase 0 | `FastApiApp` and `AppConfig` compose the current app surface. |

The web contract is [E2](../E2-http-contract/index.md); later standards decisions are [E4](../E4-standards-rebaseline/index.md). [ADR-0004](../../../adr/ADR-0004.md) keeps framework-native persistence separate. Kiln's golden-repo acceptance is [E12](../E12-kiln-acceptance/index.md).

## Considered and rejected

The old application factory was replaced by `FastApiApp`; its fluent-builder variant was rejected. FastAPI pydantic mirrors and the correlation middleware were removed. Django Phase 7's access-log middleware was removed. A framework-independent ORM base remains outside this epic.
