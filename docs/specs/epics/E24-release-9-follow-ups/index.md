# E24 — Release 9 follow-ups

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-11-17 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F24.1 — Django transfer at its limits](F24.1-django-transfer-limits.md) | Active | release-9 | 1 New · 1 Closed |
| [F24.2 — ID tokens refuse other profiles' types](F24.2-id-token-type.md) | New | release-9 | 1 New |
| [F24.3 — Declared CLI surfaces reject unknown keys](F24.3-strict-cli-surface.md) | Closed | release-9 | 1 Closed |
| [F24.4 — Specs and runbooks match the tree](F24.4-spec-and-runbook-drift.md) | New | release-9 | 1 New |

<!-- END derived features -->

Defects and spec drift found while closing
[E22](../E22-pykit-simplification/index.md), fixed before Release 9 is cut. Each
defect gets a regression test that fails today, a changelog entry under the
package's `[Unreleased]` and no other behaviour change. E22's scope constraints
apply.
