# Release 12 — Dependency updates in the release cut

|  |  |
| -- | -- |
| **Status** | in progress |
| **Start Date** | 2026-11-21 |

The release cut absorbs the open Dependabot updates: the runbook gains the step,
and the update that opened after Release 11 is taken on the release branch
([E29](../../specs/epics/E29-release-12-dependency-updates/index.md)). Patch
releases of the packages whose requirements changed carry the floors.

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 11 is shipped.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F29.1 — Dependency updates](../../specs/epics/E29-release-12-dependency-updates/F29.1-dependency-updates.md) | E29 | Active |
| [F30.1 — PostgreSQL engine and driver extras](../../specs/epics/E30-postgresql-support-in-rn-forge-sqlalchemy/F30.1-postgresql-engine-and-driver-extras.md) | E30 | New |

<!-- END derived scope -->

## Decisions

None so far.

## Breaking changes

None.

## Progress

S29.1.1 is closed. S29.1.2 takes the updates from Dependabot pull request #42.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='F29\.|S29\.'
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.
- Each patched package is tagged on the remote and installs from PyPI.
- No Dependabot pull request is open against `main`, or each open one is listed
  on this page as deferred with its reason.
