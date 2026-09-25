# E12 — Kiln acceptance

This epic tracks downstream checks that kiln owns. A gap found there may create new pykit work, but these rows are not pykit implementation tasks.

**Status:** deferred

**Readiness:** not ready

**Readiness basis:** The downstream tag-order decision below is open; kiln owns elaboration and execution of its acceptance specs.

**Owner:** kiln.

**Entry criteria:** Kiln's corresponding golden-repo, generator or release-pin work starts.

[Back to the work index](../../index.md)

| Kiln item | Source and disposition |
| --- | --- |
| `golden/python-app` | Commons D.9 acceptance. |
| `golden/python-tool` with `[lifecycle]` | Commons Part F / kiln F3.3 acceptance. |
| `golden/python-web-api` | FastAPI Phase 8 acceptance. |
| `golden/python-web-app-django` | Status-board acceptance. |
| Config manager through `StrictModel` | Commons Part G / kiln F4.2. |
| `[archetype.python-lib] packages` and `state.json` re-seed | Board / kiln F.1. |
| `oasdiff` golden-repo CI note | Board backlog, AIP-180. |
| `:verb` gateway check | Board backlog, AIP-136. |
| SQLAlchemy tag-order correction | Review second pass; depends on [F9.4](../E9-release-readiness/F9.4-batch-scope.md). |
| Old ADR and lifecycle-namespace references | Review F7; correct by meaning in kiln, not by renumbering pykit ADRs. |

**Source:** `docs/plans/reviews/docs-structure-review.md`, “Owned by kiln, tracked in E12”; `docs/plans/kiln-dependencies.md`. The [ledger](../../../plans/context.md) keeps old kiln identifiers.

## Open questions

**Q10:** Should `rn-forge-sqlalchemy` join kiln E7's tag order? The decision depends on [Q5](../E9-release-readiness/F9.4-batch-scope.md#open-questions). Do not edit kiln until the owner decides.
