# E25 — Typed application state and faster XLSX transfer

|  |  |
| -- | -- |
| **State** | Closed |
| **Start Date** | 2026-11-18 |
| **Closed Date** | 2026-11-18 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F25.1 — Typed application state](F25.1-typed-application-state.md) | Closed | release-10 | 2 Closed |
| [F25.2 — Faster XLSX transfer](F25.2-faster-xlsx-transfer.md) | Closed | release-10 | 2 Closed |

<!-- END derived features -->

Two ideas the owner took up on 2026-11-18. A FastAPI route receives its
application state through a typed dependency instead of an untyped
`request.app.state.*` read ([F25.1](F25.1-typed-application-state.md)), and an
XLSX export or import of 100,000 rows stops taking tens of seconds
([F25.2](F25.2-faster-xlsx-transfer.md)). Each feature opens with a decision
story, so the build waits for the decision, not the other way round.
