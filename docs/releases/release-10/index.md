# Release 10 — Typed application state and faster XLSX transfer

|  |  |
| -- | -- |
| **Status** | shipped |
| **Start Date** | 2026-11-18 |
| **Finish Date** | 2026-11-19 |

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
| [F25.2 — Faster XLSX transfer](../../specs/epics/E25-typed-state-and-xlsx-speed/F25.2-faster-xlsx-transfer.md) | E25 | Closed |

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

## Shipped

Shipped 2026-11-19. Every feature in scope is closed. The pull request
[#39](https://github.com/rn-forge/pykit/pull/39) merged into `main` as
`c3a16a4`, and
[run 44480605942](https://github.com/rn-forge/pykit/actions/runs/44480605942) at
`c3a16a4` passed every job, including `release`, `verify-release`, `umbrella`,
`sonar` and `docs`.

PyPI serves these versions, each with an `rn-forge-<package>-v<version>` tag at
`c3a16a4` and a published GitHub release:

| Package | Version |
| -- | -- |
| `rn-forge-data` | `0.1.5` |
| `rn-forge-fastapi` | `0.5.1` |

The other eight packages did not change and keep their Release 9 versions. Each
released package's docs at
`https://rn-forge.github.io/pykit/packages/rn-forge-<package>/latest/` serve the
new version. The `release-10` umbrella tag is created by the first `main` run
after this page says `shipped`.
