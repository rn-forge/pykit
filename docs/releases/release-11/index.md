# Release 11 — Dependency updates, Sonar debt and key-path artifacts

|  |  |
| -- | -- |
| **Status** | shipped |
| **Start Date** | 2026-11-19 |
| **Finish Date** | 2026-11-21 |

The workspace takes the open Dependabot updates, and the open Sonar issues on
`main` are fixed ([E26](../../specs/epics/E26-release-11-maintenance/index.md)).
`rn-forge-commons` 0.10.1 adds a `keys` artifact kind, for owning named key
paths in a JSON or TOML file another program also writes
([E27](../../specs/epics/E27-key-path-artifacts/index.md)). `rn-forge-tooling`
0.4.0 writes the rn-forge home's `env.sh` and links each Python tool's zsh
completion script ([E28](../../specs/epics/E28-rn-forge-home/index.md)). Patch
releases of `rn-forge-auth`, `rn-forge-cli`, `rn-forge-data`, `rn-forge-fastapi`
and `rn-forge-web` carry the dependency-floor updates.

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

## Decisions

- [ADR-0017](../../adr/ADR-0017.md): the rn-forge home is a written contract
  every installer implements, and the home owns `env.sh`.

## Breaking changes

`rn-forge-tooling` 0.4.0: `PythonTool.artifacts()` gains `completions/_<name>`,
and a `PythonTool`'s console script must answer Typer's completion variable or
the install rolls back. Otherwise none.

## Progress

All scope is closed and the release is shipped.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='F2[678]\.|S2[678]\.'
```

```text
93725c68 2026-11-20 S28.1.3, F28.1, E28 close
7bfefd3b 2026-11-20 S28.1.3 brief
620aee09 2026-11-20 S28.1.2
e44fd2af 2026-11-20 S28.1.2 brief
eae21ca0 2026-11-20 S28.1.1
1f9bdbf6 2026-11-20 S28.1.1 brief
6118339e 2026-11-20 S27.1.2, F27.1, E27 close
d6920576 2026-11-20 S27.1.2 brief
70acaafc 2026-11-20 S27.1.1
08f4d8ca 2026-11-19 S27.1.1 brief
a921e01b 2026-11-19 E27, F27.1 specs
873b2402 2026-11-19 S26.2.2, F26.2, E26 close
12450635 2026-11-19 S26.2.1
7e0a2d9d 2026-11-19 S26.2.1, S26.2.2 briefs
c446f2c8 2026-11-19 S26.1.1, F26.1 close
4f8a97c9 2026-11-19 S26.1.1 brief
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- No Dependabot pull request from the F26.1 Context table is open.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.
- `rn-forge-commons` 0.10.1 is tagged on the remote and installs from PyPI.
- `rn-forge-tooling` 0.4.0, and the patch releases `rn-forge-auth` 0.2.1,
  `rn-forge-cli` 0.2.1, `rn-forge-data` 0.1.6, `rn-forge-fastapi` 0.5.2 and
  `rn-forge-web` 0.3.3, are tagged on the remote and install from PyPI.

## Shipped

Shipped 2026-11-21. Every feature in scope is closed. The pull request
[#41](https://github.com/rn-forge/pykit/pull/41) merged into `main` as
`7b63ef85`, and
[run 44852320585](https://github.com/rn-forge/pykit/actions/runs/44852320585) at
`7b63ef85` passed every job, including `release`, `verify-release`, `umbrella`,
`sonar` and `docs`.

PyPI serves these versions (200), each with an `rn-forge-<package>-v<version>`
tag at `7b63ef85` and a published GitHub release:

| Package | Version |
| -- | -- |
| `rn-forge-auth` | `0.2.1` |
| `rn-forge-cli` | `0.2.1` |
| `rn-forge-commons` | `0.10.1` |
| `rn-forge-data` | `0.1.6` |
| `rn-forge-fastapi` | `0.5.2` |
| `rn-forge-tooling` | `0.4.0` |
| `rn-forge-web` | `0.3.3` |

The other three packages did not change and keep their earlier versions. Each
released package's docs at
`https://rn-forge.github.io/pykit/packages/rn-forge-<package>/latest/` serve the
new version. The `release-11` umbrella tag is created by the first `main` run
after this page says `shipped`.
