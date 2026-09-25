# E2 — HTTP contract

This epic records the implemented framework-neutral contract in `rn-forge-web`. Users find current behavior in that package's guides and API pages.

**Status:** done

**Owner:** pykit.

**Implemented:** `8b5160b`, `37fa7fc` (historical commits; no new tag implied).

[Back to the work index](../../index.md)

| Legacy feature | Result |
| --- | --- |
| Web Phases 0–8 | Problem details, preconditions, pagination, idempotency, readiness and public API. |
| Web Phase 9 and §9.1 | Consumer conventions and OpenAPI method naming. |
| Web Phase 10 | Auth contract and shared OIDC authenticator. A whole-auth review remains [deferred in E8](../E8-django-scope-and-auth/F8.2-auth-review.md). |
| Web Phase 11 | Framework-free conformance cases. |
| Reuse Phase 4 | Problem extensions and unmapped-exception audit. |

[ADR-0003](../../../adr/ADR-0003.md) and [ADR-0004](../../../adr/ADR-0004.md) govern the wire and framework boundary. The [ledger](../../../plans/context.md) resolves original phase details.

## Considered and rejected

Web Phase 0.2 rejected `asgi-correlation-id` and the other candidate library. The page-number and reverse-cursor proposals did not become the shared contract. The current cursor is forward-only; no `previousPageToken` is promised. Custom correlation-header handling and `Page<Item>` schema renaming were removed by [E4](../E4-standards-rebaseline/index.md).
