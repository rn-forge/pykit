# E13 — On-demand features

This epic holds proposals with a concrete trigger but no current implementation assignment. It prevents deferred rows from becoming invisible during the plan migration.

**Status:** deferred

**Readiness:** not ready

**Readiness basis:** These are proposals awaiting consumer triggers; each needs its own scope and acceptance before implementation.

**Owner:** pykit, when a named consumer supplies the need.

**Entry criteria:** Each row's stated trigger occurs; scope and acceptance are then written before implementation.

[Back to the work index](../../index.md)

| Source item | Entry criterion |
| --- | --- |
| R8 `:batchGet` and `:batchUpdate` handlers | A consumer needs handlers; spelling is already documented. |
| AIP-164 soft delete | A consumer needs `deleteTime`, `:undelete` or `showDeleted`. |
| Multi-column sorting | Owner starts composite-keyset and NULL-ordering ideation. |
| Multi-tenant row scoping | A second application states its tenancy model. |
| SQLAlchemy `AsyncIdempotencyStore`, session/unit-of-work helpers and readiness checks | A SQLAlchemy application asks for them. |
| CloudEvents envelope builder | Outbox/inbox subsystem needs it. |
| Claim-check pattern | A second storage backend is in view. |
| `ProductInstaller` shared contract | A second product needs the same contract. |
| AIP-157 `readMask` | Payload size makes partial responses necessary. |
| Django cloud messaging adapters | A second cloud backend needs an adapter. |
| Django `AUTH.OIDC` settings block | A second consumer needs configuration through the facade. |
| Django `RequestUtils` collision | A separate breaking-change plan is approved. |

**Source:** `docs/plans/README.md`, Backlog; `commons-upgrade-plan.md`, Deferred/Phase 18.4; `web-library-plan.md`, Deferred; `django-upgrade-plan.md`, Deferred/Not in this plan; `standards-rebaseline-plan.md`, R8/R9. The [ledger](../../../plans/context.md) retains each original identifier.
