# E6 — Consumer reuse

**Status:** deferred

Two pieces of plumbing that several applications each wrote for themselves: secret redaction in structured logs, and server-sent events. Both are designed and left out of release-1.

**Entry criteria:** the owner schedules either feature for a release.

[Back to the work index](../../index.md)

| Feature | Status | Scope |
| --- | --- | --- |
| [F6.1 — Structured-log redaction](F6.1-log-redaction.md) | deferred | Secret redaction in commons logging. |
| [F6.2 — Server-sent events](F6.2-sse.md) | deferred | SSE responses over `sse-starlette` in FastAPI. The dependency is approved. |

Both were left out of release-1 on 2026-09-26 ([S9.4.2](../E9-release-readiness/F9.4-batch-scope.md#s942-decide-the-consumer-reuse-features)). Each adds a module or an extra and breaks no import, so it can join any later release.

The other reuse proposals were delivered or withdrawn: see [E2](../E2-http-contract/index.md) (F2.5), [E3](../E3-framework-adapters/index.md) (F3.4) and [E4](../E4-standards-rebaseline/index.md).

## Considered and rejected

- A hand-written SSE encoder and a framework-neutral `rn_forge.web.sse` module; the `sse-starlette` evaluation retired both.
- Reuse findings 7–12 (offset pagination, work offload, SPA mounting, `serve`, a settings facade, a port container): these stay in the applications.
