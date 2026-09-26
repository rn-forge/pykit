# E2 — HTTP contract

**Status:** done · **Implemented:** 2026-09-12 to 2026-09-22 · **Owner:** pykit

The framework-neutral HTTP contract in `rn-forge-web`. The package's guides and reference pages describe current behavior.

[Back to the work index](../../index.md)

| ID | Delivered | Source | Implemented |
| --- | --- | --- | --- |
| F2.1 | Problem details, preconditions, cursor pagination, idempotency, health and the public API | Web plan Phases 0–8 | `8b5160b` |
| F2.2 | Consumer conventions and OpenAPI method naming | Web plan Phase 9 and §9.1 | `8b5160b` |
| F2.3 | Auth contract, then the shared `OidcAuthenticator`. The whole-auth review is deferred in [F8.2](../E8-django-scope-and-auth/F8.2-auth-review.md). | Web plan Phase 10 | `8b5160b`, `37fa7fc` |
| F2.4 | Framework-free conformance cases | Web plan Phase 11 | `8b5160b` |
| F2.5 | Exception-carried problem extensions and the `unmapped_exceptions` audit | Reuse plan Phase 4 | `373d6bc` |

[ADR-0001](../../../adr/ADR-0001.md) and [ADR-0005](../../../adr/ADR-0005.md) govern the wire and framework boundary. The [ledger](../../../plans/context.md) resolves original phase details.

## Considered and rejected

- `asgi-correlation-id` and `rfc9457` as dependencies (web Phase 0.2).
- Page-number pagination and a reverse cursor. Cursors are forward-only, with no `previousPageToken`.
- The custom correlation header and `Page<Item>` schema naming, later removed by [E4](../E4-standards-rebaseline/index.md).
