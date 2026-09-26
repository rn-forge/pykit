# Pykit work

What pykit is made of and what is left to do. The board says what is next; the epic says how; its ADRs say why. `done` means implemented; the [release pages](../releases/index.md) record which tags exist.

## Board

### In progress

| Epic | Release | Next step |
| --- | --- | --- |
| [E9 — Release readiness](epics/E9-release-readiness/index.md) | [release-1](../releases/release-1/index.md) | Push S9.7.1's branch pins and run its clean-install check; then S9.3.3, F9.1, F9.2, F9.8 and S9.9.4. |

### Deferred

| Epic | Entry criteria |
| --- | --- |
| [E6 — Consumer reuse](epics/E6-consumer-reuse/index.md) | The owner schedules F6.1 or F6.2 for a release. |
| [E7 — Azure adapters](epics/E7-azure-adapters/index.md) | The owner schedules the package and settles its namespace. |
| [E8 — Django scope and auth](epics/E8-django-scope-and-auth/index.md) | The owner schedules the auth review (F8.2). |
| [E11 — Framework codegen](epics/E11-framework-codegen/index.md) | The owner schedules it with a concrete framework template. |
| [E12 — On-demand features](epics/E12-on-demand-features/index.md) | Each row's own trigger. |

### Done

| Epic | Implemented |
| --- | --- |
| [E1 — Foundation and boundaries](epics/E1-foundation-and-boundaries/index.md) | 2026-09-16 |
| [E2 — HTTP contract](epics/E2-http-contract/index.md) | 2026-09-22 |
| [E3 — Framework adapters](epics/E3-framework-adapters/index.md) | 2026-09-22 |
| [E4 — Standards re-baseline](epics/E4-standards-rebaseline/index.md) | 2026-09-23 |
| [E5 — Tool lifecycle](epics/E5-tool-lifecycle/index.md) | 2026-09-22 |
| [E10 — Documentation refactor](epics/E10-documentation-refactor/index.md) | 2026-09-26 |

## Conventions

`docs/specs/_structure.md`, which the site does not publish, holds the full rules; this is the short form.

- **Taxonomy.** Epic `E<n>` → feature `F<n>.<m>` → story `S<n>.<m>.<k>`. IDs are permanent.
- **Status.** `elaborating`, `planned` (stories and a release), `in progress`, `done`, or `deferred` (with entry criteria). Stories carry their own status.
- **A decision is its own story**, so work can depend on the decision without depending on its implementation.
- **Open questions live on the feature or epic they block.** An answered question becomes an ADR or a rejected option.
- **Acceptance is checked inside pykit** ([ADR-0008](../adr/ADR-0008.md)); another repository's work never gates a feature or release.
- **Do not start or elaborate a deferred epic unless the owner asks.**

The [decision log](../adr/index.md) records the durable constraints.
