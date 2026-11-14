# Release 9 — pykit simplification

|  |  |
| -- | -- |
| **Status** | planned |

The ten packages, their tests and their documentation get simpler
([E22](../../specs/epics/E22-pykit-simplification/index.md), F22.1 to F22.13).
Shared policy gets one owner, redundant work goes, and framework adapters keep
to translation. Correctness cases get regression tests before refactoring, and
performance work starts with measurements. The
[review and proposed design](../../specs/epics/E22-pykit-simplification/design.md)
gives the evidence and tradeoffs.

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 8 is shipped.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F22.1 — Short specs with stable work records](../../specs/epics/E22-pykit-simplification/F22.1-specs.md) | E22 | New |
| [F22.2 — One current explanation per audience](../../specs/epics/E22-pykit-simplification/F22.2-documentation.md) | E22 | New |
| [F22.3 — Behavioral tests and performance baselines](../../specs/epics/E22-pykit-simplification/F22.3-tests-and-measurements.md) | E22 | New |
| [F22.4 — Commons with explicit side effects](../../specs/epics/E22-pykit-simplification/F22.4-commons.md) | E22 | New |
| [F22.5 — CLI invocation state with a clear lifetime](../../specs/epics/E22-pykit-simplification/F22.5-cli.md) | E22 | New |
| [F22.6 — Installer transactions with honest recovery](../../specs/epics/E22-pykit-simplification/F22.6-tooling.md) | E22 | New |
| [F22.7 — HTTP policy with bounded readiness](../../specs/epics/E22-pykit-simplification/F22.7-web.md) | E22 | New |
| [F22.8 — Auth policy and bounded caches](../../specs/epics/E22-pykit-simplification/F22.8-auth.md) | E22 | New |
| [F22.9 — Django adapters with safe parsing and ownership](../../specs/epics/E22-pykit-simplification/F22.9-django.md) | E22 | New |
| [F22.10 — FastAPI adapters with clear validation boundaries](../../specs/epics/E22-pykit-simplification/F22.10-fastapi.md) | E22 | New |
| [F22.11 — SQLAlchemy bulk work with explicit bounds](../../specs/epics/E22-pykit-simplification/F22.11-sqlalchemy.md) | E22 | New |
| [F22.12 — Tabular helpers without redundant copies](../../specs/epics/E22-pykit-simplification/F22.12-data.md) | E22 | New |
| [F22.13 — Small release utilities with one metadata path](../../specs/epics/E22-pykit-simplification/F22.13-devops.md) | E22 | New |

<!-- END derived scope -->

## Order

The order follows
[E22's Order](../../specs/epics/E22-pykit-simplification/index.md#order): F22.3
first, then the correctness cases and F22.4 to F22.13, with F22.2 and F22.1
last.

## Shipped

Filled at the cut.
