# Pykit work

This board summarizes ownership, progress and specification readiness. Decisions, dependencies and acceptance live in the linked specs.

`not ready` means the specification needs decisions or elaboration before implementation. Follow the epic for individual feature readiness.

**Status:** in progress

**Owner:** pykit.

`done` means the implementation or decision is recorded. It does not mean a new package tag exists. The [release index](../releases/index.md) owns batch scope and release evidence.

## Planned

| Epic | Owner | Readiness |
| --- | --- | --- |
| [E6 — Consumer reuse](epics/E6-consumer-reuse/index.md) | pykit | not ready |
| [E9 — Release readiness](epics/E9-release-readiness/index.md) | pykit release owner | not ready |

## Deferred

| Epic | Owner | Readiness |
| --- | --- | --- |
| [E7 — Azure adapters](epics/E7-azure-adapters/index.md) | pykit owner | not ready |
| [E8 — Django scope and auth](epics/E8-django-scope-and-auth/index.md) | pykit owner | not ready |
| [E11 — Framework codegen](epics/E11-framework-codegen/index.md) | kiln integration | not ready |
| [E12 — Kiln acceptance](epics/E12-kiln-acceptance/index.md) | kiln | not ready |
| [E13 — On-demand features](epics/E13-on-demand-features/index.md) | pykit on consumer request | not ready |

## Done

| Epic | Owner | Implementation evidence |
| --- | --- | --- |
| [E1 — Foundation and boundaries](epics/E1-foundation-and-boundaries/index.md) | pykit | Commits in epic; no new tag claimed |
| [E2 — HTTP contract](epics/E2-http-contract/index.md) | pykit | Commits in epic; no new tag claimed |
| [E3 — Framework adapters](epics/E3-framework-adapters/index.md) | pykit | Commits in epic; no new tag claimed |
| [E4 — Standards re-baseline](epics/E4-standards-rebaseline/index.md) | pykit | Commits in epic; deferred tails have separate owners |
| [E5 — Tool lifecycle](epics/E5-tool-lifecycle/index.md) | pykit | Commits in epic; kiln acceptance separate |
| [E10 — Documentation refactor](epics/E10-documentation-refactor/index.md) | pykit documentation refactor | Five batches completed in this working tree; no commit or release claimed |

Old Phase, D and R identifiers resolve through the [migration ledger](../plans/context.md). The [decision log](../adr/index.md) records the enduring constraints.
