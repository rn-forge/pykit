# E13 — On-demand features

**Status:** deferred · **Owner:** pykit

Proposals that wait for a named consumer. Each has a trigger; when it fires, the item gets its own feature file with stories and acceptance before any code.

**Entry criteria:** the row's trigger occurs.

[Back to the work index](../../index.md)

| ID | Proposal | Trigger | Source |
| --- | --- | --- | --- |
| F13.1 | `:batchGet` and `:batchUpdate` handlers; the spelling is already documented | A consumer needs the handlers. | `standards-rebaseline-plan.md`, R8 (AIP-231, AIP-234) |
| F13.2 | Soft delete in AIP-164's shape: `deleteTime`, `:undelete`, `showDeleted`. Conflicts with the status-based soft delete in F13.13; whichever is promoted first settles the other. | A consumer needs soft delete on the wire. | `standards-rebaseline-plan.md`, R8 (AIP-164) |
| F13.3 | Multi-column sorting, with composite keysets and NULL ordering | The owner starts the ideation. | `standards-rebaseline-plan.md`, R8 |
| F13.4 | Multi-tenant row scoping | A second application states its tenancy model. | `web-library-plan.md` and `fastapi-library-plan.md`, "Deferred — do not build these yet" |
| F13.5 | SQLAlchemy `AsyncIdempotencyStore`, session and unit-of-work helpers, readiness checks | A SQLAlchemy application asks for them. | `standards-rebaseline-plan.md`, R9 |
| F13.6 | CloudEvents envelope builder | The outbox/inbox subsystem needs one. | `commons-upgrade-plan.md`, "Deferred — do not build these yet" |
| F13.7 | Claim-check pattern | A second storage backend is in view. | `commons-upgrade-plan.md` and `django-upgrade-plan.md`, "Deferred — do not build these yet" |
| F13.8 | A shared `ProductInstaller` contract. Shared installer mechanics stay in `rn-forge-tooling`: do not create `rn-forge-selfkit`. | A second product needs the same contract. | `commons-upgrade-plan.md`, Phase 18.4; `plan-board.md`, "Gated decisions" |
| F13.9 | AIP-157 `readMask` partial responses | Payload size makes partial responses necessary. | `standards-rebaseline-plan.md`, R8 |
| F13.10 | Django cloud messaging adapters | A second cloud backend needs an adapter. | `django-upgrade-plan.md`, "Deferred — do not build these yet" |
| F13.11 | Django `AUTH.OIDC` settings block | A second consumer needs OIDC configuration through the settings facade. | `django-upgrade-plan.md`, "Deferred — do not build these yet" |
| F13.12 | Fix the Django `RequestUtils` name collision | A breaking-change plan is approved. | `django-upgrade-plan.md`, "Not in this plan (deliberately deferred)" |
| F13.13 | A shared model vocabulary for SQLAlchemy: audit-column semantics, a shared `status` enumeration, natural-key rules and status-based soft delete, normative for both ORM packages | An application needs one of these to behave the same on Django and SQLAlchemy. | `model-conventions.md` |

F13.13 preserves the normative model conventions the refactor removed from `rn-forge-web`'s model conventions guide. The owner kept that page advisory on 2026-09-25; the archived page holds the full rules, and the [ledger](../../../plans/context.md) lists each one.

Every file in the Source column is in `plans/archive/`. The ledger keeps each original identifier.
