# Spec routing

All pykit work has one epic under `epics/E<n>-<slug>/`. Active features use `F<n>.<m>-<slug>.md` beside the epic index. Deferred work has entry criteria; kiln-owned acceptance stays clearly labelled.

Current behavior belongs in package docs or root `architecture/`. Decisions belong in `adr/`. Release assignments live only in `releases/`. `plans/context.md` maps old identifiers and history.

## Status and readiness

Use `planned`, `elaborating`, `in progress`, `done` and `deferred` as progress status values. `done` records implementation evidence; it does not imply a package tag.

Every unfinished epic and feature carries a separate `**Readiness:** ready` or `**Readiness:** not ready` line and a short `**Readiness basis:**`. Readiness describes whether its specification is settled enough to implement, not whether work has started or been released. Completed work does not need a readiness marker.

- Unresolved scope, design or acceptance questions belong in `## Open questions` on the owning spec and make it `not ready`. Missing implementation scope or acceptance also makes it `not ready`.
- Keep questions authoritative in one spec. Other specs link to that section instead of repeating the question. Preserve existing question IDs.
- A feature depending on an unresolved shared decision is `not ready`; name the owning spec in its readiness basis. A settled spec may be `ready` while execution awaits a dependency, scheduling or permission recorded under `Depends on` or `Entry criteria`.
- An epic is `not ready` if a shared decision or any unfinished feature is not ready. Its feature table summarizes each feature's readiness; ready features may proceed independently where dependencies allow.
- The board summarizes progress and readiness only. It contains no question text, question IDs or open-question counts. Readers follow the epic to its specs.
- Release-selection questions live in the release-scope spec. Selection alone does not make an otherwise complete implementation spec unready.
- Resolve questions in their owning spec before marking it ready, and update epic, board and affected release readiness summaries together. Record durable decisions in ADRs; retain rejected options with the spec.
