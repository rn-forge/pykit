# E6 — Consumer reuse

This epic holds two shared features that applications have asked to reuse. It is for implementers and the owner deciding when to schedule them.

**Status:** planned

**Readiness:** not ready

**Readiness basis:** Both features need their acceptance or design settled; see their readiness rows below. Release selection alone is not an implementation blocker.

**Owner:** pykit.

**Depends on:** A named consuming application for acceptance.

[Back to the work index](../../index.md)

| Feature | Status | Readiness | Scope |
| --- | --- | --- | --- |
| [F6.1 — Structured-log redaction](F6.1-log-redaction.md) | planned | not ready | Secret redaction in commons logging. |
| [F6.2 — Server-sent events](F6.2-sse.md) | planned | not ready | SSE frames over `sse-starlette` in FastAPI. |

Implemented or withdrawn reuse proposals are recorded in [E3](../E3-framework-adapters/index.md) and [E4](../E4-standards-rebaseline/index.md). Account Portal and IntelliBuild acceptance waits for those applications to resume; this is consumer-owned acceptance, not a pykit implementation task.

## Readiness dependencies

The redaction and SSE questions live in [F6.1](F6.1-log-redaction.md#open-questions) and [F6.2](F6.2-sse.md#open-questions). [F9.4](../E9-release-readiness/F9.4-batch-scope.md#open-questions) owns release selection. Neither feature has a release assignment; if deferred, retain its ID.

## Considered and rejected

The hand-written SSE encoder and web-owned `sse` module were rejected during the library evaluation. Reuse findings 7–12 remain with applications. The abandoned OpenAPI helpers and correlation-ID validation are historical items in [E4](../E4-standards-rebaseline/index.md).
