# E16 — kiln adoption

| | |
| --- | --- |
| **State** | Active |
| **Start Date** | 2026-10-15 |

pykit moves onto [kiln](https://github.com/rn-forge/kiln)'s `python-lib` archetype, so that its CI, task surface and docs tooling are generated and checked like every other rn-forge repository, and pykit stops carrying its own copies. kiln proves the archetype can host pykit inside kiln (kiln's F6.1 and F6.4); this epic is pykit's side: the planner moves to where a generated workflow can reach it, pykit conforms to the shared standard where it does not yet, and then the cutover. Acceptance is checked inside pykit ([ADR-0008](../../../adr/ADR-0008.md)).

[Back to the work index](../../index.md)

| Feature | Scope | State |
| --- | --- | --- |
| [F16.1 — The workspace planner ships in rn-forge-devops](F16.1-devops-package.md) | A new `rn-forge-devops` package holds `.github/scripts/workspace_ci.py` as a platform- and stack-neutral core with uv and GitHub Actions adapters, released as 0.1.0. Unblocks kiln's F6.4. | Active |
| [F16.2 — pykit passes the shared standard](F16.2-conform-to-the-standard.md) | Current lint and type tools, mdformat-clean Markdown, Keep a Changelog headings. | New |
| [F16.3 — Cut over onto kiln](F16.3-cutover.md) | `kiln init` as `python-lib`, generated CI and tasks, and the files pykit stops owning. | New |

[ADR-0012](../../../adr/ADR-0012.md) records that CI and release logic ships as `rn-forge-devops`, never as workflow logic or copied scripts. kiln's matching decisions are its ADR-0014 (the planner, the `ci:*` tasks, workspace members in the dependency contract, a workspace that owns its import contracts) and ADR-0006 (generated CI runs the pinned kiln read-only).

## Considered and rejected

- **Keep pykit hand-managed.** pykit's E14 pipeline is the reference kiln's `python-lib` CI is built from. Two copies drift, and pykit would keep its own Dependabot, setup action and board script while every other repository gets kiln's.
- **Bend kiln to pykit's current layout.** Where pykit differs from the standard only by habit (Markdown style, changelog headings, a stale lint baseline), pykit changes (F16.2). kiln changes only where pykit's shape is one any library workspace can have: members that depend on each other, namespace packages and a repository that owns its import contracts.
