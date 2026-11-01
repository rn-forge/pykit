# E6 — Consumer reuse

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-31 |

Two pieces of plumbing that several applications each wrote for themselves:
secret redaction in structured logs, and server-sent events.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F6.1 — Structured-log redaction](F6.1-log-redaction.md) | Secret redaction in commons logging. | New |
| [F6.2 — Server-sent events](F6.2-sse.md) | SSE responses over `sse-starlette` in FastAPI. The dependency is approved. | Active |

Both were left out of release-1 on 2026-09-26
([S9.4.2](../E9-release-readiness/F9.4-batch-scope.md#s942-decide-the-consumer-reuse-features))
and joined [Release 8](../../../releases/release-8/index.md) on 2026-10-31. Each
adds a module or an extra and breaks no import.

The other reuse proposals were delivered or withdrawn: see
[E2](../E2-http-contract/index.md) (F2.5),
[E3](../E3-framework-adapters/index.md) (F3.4) and
[E4](../E4-standards-rebaseline/index.md).

## Considered and rejected

- A hand-written SSE encoder and a framework-neutral `rn_forge.web.sse` module;
  the `sse-starlette` evaluation retired both.
- Reuse findings 7–12 (offset pagination, work offload, SPA mounting, `serve`, a
  settings facade, a port container): these stay in the applications.
