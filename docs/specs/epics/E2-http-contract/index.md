# E2 — HTTP contract

**Status:** done · **Implemented:** 2026-09-12 to 2026-09-22

The framework-neutral HTTP contract in `rn-forge-web`. The package's guides and reference pages describe current behavior.

[Back to the work index](../../index.md)

| ID | Delivered | Implemented |
| --- | --- | --- |
| F2.1 | Problem details, preconditions, cursor pagination, idempotency, health and the public API | `8b5160b` |
| F2.2 | Consumer conventions and OpenAPI method naming | `8b5160b` |
| F2.3 | Auth contract, then the shared `OidcAuthenticator`. The whole-auth review is [E13](../E13-auth/index.md). | `8b5160b`, `37fa7fc` |
| F2.4 | Framework-free conformance cases | `8b5160b` |
| F2.5 | Exception-carried problem extensions and the `unmapped_exceptions` audit | `373d6bc` |

[ADR-0001](../../../adr/ADR-0001.md) and [ADR-0005](../../../adr/ADR-0005.md) govern the wire and framework boundary.

## Considered and rejected

- `asgi-correlation-id` and `rfc9457` as dependencies.
- Page-number pagination and a reverse cursor. Cursors are forward-only, with no `previousPageToken`.
- The custom correlation header and `Page<Item>` schema naming, later removed by [E4](../E4-standards-rebaseline/index.md).
