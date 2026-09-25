# Kiln handoff: historical record and current pointers

This page keeps the stable handoff path that kiln cites. It records what kiln expected from pykit in the 2026-09-12 plan and directs readers to the current owners of work and decisions.

**Status:** done
**Original date:** 2026-09-12
**Normalized:** 2026-09-24
**Owner:** pykit for this record; kiln for downstream acceptance.

## Current destinations

| Concern | Current home |
| --- | --- |
| Live pykit status and open questions | [Spec board](../specs/index.md) |
| Package graph and import fences | [Workspace architecture](../architecture/workspace.md), [ADR-0001](../adr/ADR-0001.md) |
| Pinned Git tags and release evidence | [ADR-0002](../adr/ADR-0002.md), [E9 release readiness](../specs/epics/E9-release-readiness/index.md), [release index](../releases/index.md) |
| Tool lifecycle contract | [ADR-0005](../adr/ADR-0005.md), [E5 tool lifecycle](../specs/epics/E5-tool-lifecycle/index.md), the `rn-forge-tooling` lifecycle guide |
| Framework code generators | [E11 framework code generation](../specs/epics/E11-framework-codegen/index.md) |
| Kiln-owned golden repositories and handoffs | [E12 kiln acceptance](../specs/epics/E12-kiln-acceptance/index.md) |
| Source-by-source history | [Migration ledger](context.md) |

The original handoff text is preserved in Git history. The [migration ledger](context.md) records its baseline hash and maps its sections. Its commands and old package layouts are historical evidence, not instructions for current work.

## Historical milestones

| Original handoff item | Pykit disposition | Kiln ownership |
| --- | --- | --- |
| Phase A: commons stabilization | Implemented in commons Part C (`28bef7f`). | None recorded. |
| Phase C: first tooling extraction | Landed at `4624bfe`; the boundary was corrected in Phase C.2. | None recorded. |
| Phase C.2: defects, three-layer split (D52), docs-policy extraction (A2), layout (D55), CI and pinned dependency contract (F9/F14) | Implemented at `f59c40f`; later CLI layout changes are recorded in [E1](../specs/epics/E1-foundation-and-boundaries/index.md). | Kiln owns its policy and generated repository inputs. |
| Phase C.3: tool lifecycle | Installer mechanics implemented at `757908e`; the CLI-owned lifecycle table was retired at `1a8241b`. | `golden/python-tool` acceptance in [E12](../specs/epics/E12-kiln-acceptance/index.md). |
| Kiln F4.2: strict pydantic config models | Commons `StrictModel` implemented at `231a68e` behind an optional extra. | Kiln config-manager adoption in [E12](../specs/epics/E12-kiln-acceptance/index.md). |
| FastAPI Phase 8 | Adapter implementation committed at `3e80dbd`; no new pykit implementation is assigned to Phase 8. | `golden/python-web-api` acceptance in [E12](../specs/epics/E12-kiln-acceptance/index.md). |
| Kiln E7: release pin flip | Pykit release preparation belongs to [E9](../specs/epics/E9-release-readiness/index.md). | Kiln starts its pin flip when the owner declares pykit stable. |

These commit IDs describe implementation evidence. They do not identify released tags or certify a current validation run.

## Downstream corrections for kiln

Kiln owns the following updates. [E12](../specs/epics/E12-kiln-acceptance/index.md) tracks their status; this page preserves the handoff detail.

| Kiln reference or acceptance | Correction |
| --- | --- |
| The old `cli-lifecycle-namespace-plan.md` and `golden/python-tool` | Use tooling's sibling `[lifecycle]` table and `build_tool_app`. The old CLI-owned `[cli.lifecycle]` table and `target` field were retired. The [historical forwarding page](cli-lifecycle-namespace-plan.md) retains kiln's known path. |
| Old descriptive ADR filenames and references to ADR-0009/0011 | Resolve each reference by decision meaning against kiln's current ADR log and this repo's [decision index](../adr/index.md). Pykit ADR numbers are independent; do not renumber by matching numbers. |
| `golden/python-app` and `golden/python-web-app-django` | Keep these as kiln-owned acceptance, with any discovered pykit gap returning as a new feature. |
| Kiln F4.2, F.1 and AIP-180/AIP-136 golden checks | Adopt `StrictModel`; handle package-list/state re-seed, OpenAPI diff and gateway checks in kiln's own work. Their detailed source rows are in [E12](../specs/epics/E12-kiln-acceptance/index.md). |
| Kiln E7 tag order | Its recorded order omits `rn-forge-sqlalchemy`. [F9.4](../specs/epics/E9-release-readiness/F9.4-batch-scope.md) keeps first-batch scope open (Q5). Kiln's correction (Q10) remains conditional on that answer. |

## Decisions and release boundary

The original D52/D55 notes describe the three-layer split and grouped modules. [ADR-0001](../adr/ADR-0001.md) and the [workspace graph](../architecture/workspace.md) describe their current result, including `rn-forge-sqlalchemy`. The original D37 code-generator placement is a [deferred feature](../specs/epics/E11-framework-codegen/index.md); import fences exist, but generators do not. Kiln owns archetypes, golden repositories and product policy. `rn-forge-tooling` owns reusable generation and installation mechanics.

The release trigger remains kiln E7's owner declaration. Pykit's [tag cut](../specs/epics/E9-release-readiness/F9.6-tag-cut.md) needs the owner's approval. The Django split outcome ([F8.1](../specs/epics/E8-django-scope-and-auth/F8.1-django-split.md), Q4), first-batch package scope ([F9.4](../specs/epics/E9-release-readiness/F9.4-batch-scope.md), Q5), and SQLAlchemy kiln tag-order correction (Q10) remain open. Log redaction and server-sent events have no release assignment while [Q9](../specs/epics/E6-consumer-reuse/index.md) remains open.
