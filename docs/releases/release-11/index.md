# Release 11 — Dependency updates, Sonar debt and key-path artifacts

|  |  |
| -- | -- |
| **Status** | planned |
| **Start Date** | 2026-11-19 |

The workspace takes the open Dependabot updates, and the open Sonar issues on
`main` are fixed ([E26](../../specs/epics/E26-release-11-maintenance/index.md)).
`rn-forge-commons` 0.10.1 adds a `keys` artifact kind, for owning named key
paths in a JSON or TOML file another program also writes
([E27](../../specs/epics/E27-key-path-artifacts/index.md)). `rn-forge-tooling`
0.4.0 writes the rn-forge home's `env.sh` and links each Python tool's zsh
completion script ([E28](../../specs/epics/E28-rn-forge-home/index.md)).

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 10 is shipped.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F26.1 — Dependency updates](../../specs/epics/E26-release-11-maintenance/F26.1-dependency-updates.md) | E26 | Closed |
| [F26.2 — Sonar debt](../../specs/epics/E26-release-11-maintenance/F26.2-sonar-debt.md) | E26 | Closed |
| [F27.1 — A `keys` artifact kind](../../specs/epics/E27-key-path-artifacts/F27.1-keys-artifact-kind.md) | E27 | Closed |
| [F28.1 — The home contract, `env.sh` and zsh completions](../../specs/epics/E28-rn-forge-home/F28.1-home-contract-and-completions.md) | E28 | Closed |

<!-- END derived scope -->

## Order

S26.1.1 first: its bumps can move ruff and pyright findings that F26.2 then
fixes. S26.2.1 and S26.2.2 are independent of each other. S27.1.1 before
S27.1.2, which prepares the `rn-forge-commons` 0.10.1 release. S28.1.1 before
S28.1.2 and S28.1.3; S28.1.3 prepares the `rn-forge-tooling` 0.4.0 release.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='F2[678]\.|S2[678]\.'
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- No Dependabot pull request from the F26.1 Context table is open.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.
- `rn-forge-commons` 0.10.1 is tagged on the remote and installs from PyPI.
