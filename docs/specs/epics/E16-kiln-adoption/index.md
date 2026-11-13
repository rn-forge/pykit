# E16 — kiln adoption

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-15 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F16.1 — The workspace planner ships in rn-forge-devops](F16.1-devops-package.md) | Closed | release-4 | 3 Closed |
| [F16.2 — pykit passes the shared standard](F16.2-conform-to-the-standard.md) | Closed | release-4 | 3 Closed |
| [F16.3 — Cut over onto kiln](F16.3-cutover.md) | Active | release-8 | 2 New · 8 Closed · 2 Removed |
| [F16.4 — Every member passes its own gate](F16.4-member-gate.md) | Closed | release-5 | 3 Closed |
| [F16.5 — rn-forge-devops meets kiln's CI contract](F16.5-devops-meets-kiln-ci.md) | Closed | release-5 | 3 Closed |
| [F16.6 — Retire the plan outputs generated CI does not read](F16.6-retire-unread-plan-outputs.md) | New | release-8 | 1 New |
| [F16.7 — Instruction files follow kiln's standard](F16.7-instructions-follow-kiln-standard.md) | New | release-8 | 1 New |

<!-- END derived features -->

pykit moves onto [kiln](https://github.com/rn-forge/kiln)'s `python-lib`
archetype, so that its CI, task surface and docs tooling are generated and
checked like every other rn-forge repository, and pykit stops carrying its own
copies. kiln proves the archetype can host pykit inside kiln (kiln's F6.1 and
F6.4); this epic is pykit's side: the planner moves to where a generated
workflow can reach it, pykit conforms to the shared standard where it does not
yet, and then the cutover. Acceptance is checked inside pykit
([ADR-0008](../../../adr/ADR-0008.md)).

pykit cuts over on kiln's `feature/v1`, before the `v0.1.0` tag, so kiln keeps
being refined from pykit's findings. The hand-written `main.yml`,
`internal-ranges.yml`, `umbrella-release.yml` and `broker-profile.yml` are all
deleted, not kept: kiln's checks and its `integration` services cover them.
[F16.3](F16.3-cutover.md) holds the exact steps; its S16.3.1 is the one list a
rerun executes.

The cutover runs on `feature/kiln-cutover`, cut from `feature/release-8`. Its
commits are F16.3 Refinement, S16.3.11 (the format commit), and S16.3.1's path
groups, the documentation first. The branch merges back into `feature/release-8`
with `git merge --no-ff`; only `feature/release-8` → `main` waits for the tag.

[Back to the work index](../../index.md)

[ADR-0012](../../../adr/ADR-0012.md) records that CI and release logic ships as
`rn-forge-devops`, never as workflow logic or copied scripts. kiln's matching
decisions are its ADR-0014 (the planner, the `ci:*` tasks, workspace members in
the dependency contract, a workspace that owns its import contracts) and
ADR-0006 (generated CI runs the pinned kiln read-only).

## Considered and rejected

- **Keep pykit hand-managed.** pykit's E14 pipeline is the reference kiln's
  `python-lib` CI is built from. Two copies drift, and pykit would keep its
  own Dependabot, setup action and board script while every other repository
  gets kiln's.
- **Bend kiln to pykit's current layout.** Where pykit differs from the standard
  only by habit (Markdown style, changelog headings, a stale lint baseline),
  pykit changes (F16.2). kiln changes only where pykit's shape is one any
  library workspace can have: members that depend on each other, namespace
  packages and a repository that owns its import contracts.
