# E4 — Standards re-baseline

**Status:** done · **Implemented:** 2026-09-22 to 2026-09-23 · **Owner:** pykit

The standards and native-framework decisions applied across web, Django, FastAPI and SQLAlchemy. Package docs state the current contract.

[Back to the work index](../../index.md)

| ID | Delivered | Source | Implemented |
| --- | --- | --- | --- |
| F4.1 | OpenAPI accuracy, standards deviations fixed, shared web logic and the service surface (health, discovery, deprecation, conditional GET, `Retry-After`, security headers, body limit, CORS, idempotency runner) | R1, R2, R2.5 | `373d6bc` |
| F4.2 | W3C Trace Context through OpenTelemetry as the only request correlation; `X-Correlation-ID` is neither read nor sent ([ADR-0001](../../../adr/ADR-0001.md), rule 5) | R3 | `630142c` |
| F4.3 | One wire model per stack, as pydantic models in `rn-forge-web` | R4 | `df7a245` |
| F4.4 | Library evaluations, each closed with a recorded exemption | R5 | `74b36ff`, `c1979a4` |
| F4.5 | Tabular transfer over `tablib` and `django-import-export`, and FastAPI transfer | R7 | `cc78e19`, `a036a50` |
| F4.6 | API Improvement Proposal conventions where no RFC applies: sorting, field names, timestamps, long-running operations | R8 | `9af1705` |
| F4.7 | `rn-forge-sqlalchemy` and cross-stack tabular work | R9 | `653ac47` |
| F4.8 | Simplification after R3: access log removed, OpenTelemetry log processor moved to commons, `traceId` rename | R10 | `74b36ff` |

R6, the Django scope review, was not delivered here: the split decision is [F8.1](../E8-django-scope-and-auth/F8.1-django-split.md), the auth review is [F8.2](../E8-django-scope-and-auth/F8.2-auth-review.md), and R7 settled transfer. The remaining R8 and R9 items are deferred in [E13](../E13-on-demand-features/index.md).

[ADR-0001](../../../adr/ADR-0001.md) states the order of authority. [ADR-0005](../../../adr/ADR-0005.md) states the shared HTTP contract. F4.2 emits `traceresponse` from Trace Context Level 2, a Candidate Recommendation that OpenTelemetry Python marks experimental; that instability is accepted. The [ledger](../../../plans/context.md) keeps each R item, its evidence and conflicts.

## Considered and rejected

- Reuse Phase 1's OpenAPI component helpers and `Page<Item>` renaming, withdrawn by R1.
- Custom correlation-ID handling and reuse Phase 5's validator, withdrawn by R3. Keeping `X-Correlation-ID` through `asgi-correlation-id`, or as an alias beside Trace Context, was rejected with it: no standard names the header, and two correlation values can disagree.
- Starlette's body-limit middleware (R10.3), rejected at its probe; the kit's problem response remains.
- The R5 and R9 library candidates, each exempt with its reason in the ledger.
- AIP-193, 154, 155, 134, 160 and 122, where an RFC or a native mechanism already governs.
