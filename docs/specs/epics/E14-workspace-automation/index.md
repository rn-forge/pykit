# E14 — Workspace automation

|  |  |
| -- | -- |
| **State** | Closed |
| **Start Date** | 2026-09-28 |
| **Closed Date** | 2026-10-03 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F14.1 — Discovered pipeline](F14.1-discovered-pipeline.md) | Closed | release-2 | 5 Closed |
| [F14.2 — Pipeline hardening](F14.2-pipeline-hardening.md) | Closed | release-2 | 8 Closed |
| [F14.3 — Generated board](F14.3-generated-board.md) | Closed | release-2 | 3 Closed |
| [F14.4 — Sonar remediation and analysis targeting](F14.4-sonar-remediation.md) | Closed | release-2 | 7 Closed |

<!-- END derived features -->

Repository automation that reads the workspace instead of naming its parts, so
it can be copied into another repository of the same shape. The CI pipeline
finds the packages from the uv manifests and runs any uv monorepo of separately
released packages; the spec board is generated from the epic and feature pages
and fails on inconsistent specs. pykit is the reference; kiln's golden templates
adopt it from here.

[Back to the work index](../../index.md)

The owner requested F14.1 and F14.2 on 2026-09-28, and F14.3 on 2026-09-29.
