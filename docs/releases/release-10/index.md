# Release 10 — Typed application state and faster XLSX transfer

|  |  |
| -- | -- |
| **Status** | planned |
| **Start Date** | 2026-11-18 |

`rn-forge-fastapi` gets a typed application-state dependency, and
`rn-forge-data` reads and writes large XLSX tables faster
([E25](../../specs/epics/E25-typed-state-and-xlsx-speed/index.md)).

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 9 is shipped.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F25.1 — Typed application state](../../specs/epics/E25-typed-state-and-xlsx-speed/F25.1-typed-application-state.md) | E25 | Closed |
| [F25.2 — Faster XLSX transfer](../../specs/epics/E25-typed-state-and-xlsx-speed/F25.2-faster-xlsx-transfer.md) | E25 | New |

<!-- END derived scope -->

## Order

F25.1 and F25.2 are independent. Within each, the decision story comes first:
S25.1.1 before S25.1.2, and S25.2.1 before S25.2.2.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='F25\.|S25\.'
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.
