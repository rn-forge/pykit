# E4 — Standards re-baseline

This epic records the standards and native-framework decisions implemented across web, Django, FastAPI and SQLAlchemy. Package docs state the current contract.

**Status:** done

**Owner:** pykit.

**Implemented:** `373d6bc`, `630142c`, `74b36ff`, `c1979a4`, `df7a245`, `cc78e19`, `a036a50`, `9af1705`, `653ac47` (historical commits; no new tag implied).

[Back to the work index](../../index.md)

| Legacy item | Disposition |
| --- | --- |
| R1–R2.5 | OpenAPI accuracy, wire corrections, shared logic and service surface implemented. |
| R3 | W3C Trace Context through OpenTelemetry implemented. |
| R4 | Shared wire models implemented in `rn-forge-web`. |
| R5 | Library evaluations closed with exemptions; no dependency adopted from those evaluations. |
| R6 | Django split decision and whole-auth review live in [E8](../E8-django-scope-and-auth/index.md); transfer scope settled by R7. |
| R7 | `tablib` and `django-import-export` transfer work implemented. |
| R8 | API Improvement Proposal conventions implemented where chosen; on-demand tails live in [E13](../E13-on-demand-features/index.md). |
| R9 | `rn-forge-sqlalchemy` and cross-stack tabular work implemented; remaining helpers are deferred in [E13](../E13-on-demand-features/index.md). |
| R10 | Simplification implemented except the rejected R10.3 probe. |

[ADR-0003](../../../adr/ADR-0003.md) states the order of authority. [ADR-0004](../../../adr/ADR-0004.md) states the shared HTTP and separate ORM boundary. The [ledger](../../../plans/context.md) retains each R item, its evidence and conflicts.

## Considered and rejected

R1 withdrew reuse Phase 1 and the `Page<Item>` renaming. R3 withdrew custom correlation-ID handling and reuse Phase 5. R10.2 removed access-log middleware. R10.3 rejected Starlette's body-limit middleware at its probe, so the kit's problem response remains. R5 and R9 library candidates were exempt. R8 rejected AIP alternatives where existing RFCs or native mechanisms govern.
