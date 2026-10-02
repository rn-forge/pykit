# E14 — Workspace automation

| | |
| --- | --- |
| **State** | Active |
| **Start Date** | 2026-09-28 |

Repository automation that reads the workspace instead of naming its parts, so it can be copied into another repository of the same shape. The CI pipeline finds the packages from the uv manifests and runs any uv monorepo of separately released packages; the spec board is generated from the epic and feature pages and fails on inconsistent specs. pykit is the reference; kiln's golden templates adopt it from here.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| --- | --- | --- |
| [F14.1 — Discovered pipeline](F14.1-discovered-pipeline.md) | Plan every job from the manifests; keep per-package release gating. | Active |
| [F14.2 — Pipeline hardening](F14.2-pipeline-hardening.md) | Release record and resume, plan base from the last green run, SHA pins, setup action, concurrency, Sonar gate, timeouts, Dependabot. | Active |
| [F14.3 — Generated board](F14.3-generated-board.md) | `docs/_update_board.sh` writes the board's Releases and Backlog sections and each release's Scope table, and fails on inconsistent specs; the hand-maintained epic groups go. | Closed |

The owner requested F14.1 and F14.2 on 2026-09-28, and F14.3 on 2026-09-29.
