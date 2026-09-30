# E4 — Standards re-baseline

| | |
| --- | --- |
| **State** | Closed |
| **Start Date** | 2026-09-22 |
| **Closed Date** | 2026-09-23 |

The standards and native-framework decisions applied across web, Django, FastAPI and SQLAlchemy. Package docs state the current contract.

[Back to the work index](../../index.md)

| ID | Scope | Commits | State |
| --- | --- | --- | --- |
| F4.1 | OpenAPI accuracy, standards deviations fixed, shared web logic and the service surface (health, discovery, deprecation, conditional GET, `Retry-After`, security headers, body limit, CORS, idempotency runner) | `373d6bc` | Closed |
| F4.2 | W3C Trace Context through OpenTelemetry as the only request correlation; `X-Correlation-ID` is neither read nor sent ([ADR-0001](../../../adr/ADR-0001.md), rule 5) | `630142c` | Closed |
| F4.3 | One wire model per stack, as pydantic models in `rn-forge-web` | `df7a245` | Closed |
| F4.4 | Library evaluations, each closed with a recorded exemption | `74b36ff`, `c1979a4` | Closed |
| F4.5 | Tabular transfer over `tablib` and `django-import-export`, and FastAPI transfer | `cc78e19`, `a036a50` | Closed |
| F4.6 | API Improvement Proposal conventions where no RFC applies: sorting, field names, timestamps, long-running operations | `9af1705` | Closed |
| F4.7 | `rn-forge-sqlalchemy` and cross-stack tabular work | `653ac47` | Closed |
| F4.8 | Simplification after F4.2: access log removed, OpenTelemetry log processor moved to commons, `traceId` rename | `74b36ff` | Closed |

The Django scope review was not delivered here: the split decision is parked in the [ideas list](../../ideas.md#django-optional-areas) and the auth review is [E13](../E13-auth/index.md). The remaining API-convention items are deferred in [E12](../E12-http-contract-extensions/index.md), and the SQLAlchemy items are parked in the [ideas list](../../ideas.md).

[ADR-0001](../../../adr/ADR-0001.md) states the order of authority. [ADR-0005](../../../adr/ADR-0005.md) states the shared HTTP contract. F4.2 emits `traceresponse` from Trace Context Level 2, a Candidate Recommendation that OpenTelemetry Python marks experimental; that instability is accepted.

## Considered and rejected

- OpenAPI component helpers and `Page<Item>` schema naming, withdrawn by F4.1.
- Custom correlation-ID handling and its validator, withdrawn by F4.2. Keeping `X-Correlation-ID` through `asgi-correlation-id`, or as an alias beside Trace Context, was rejected with it: no standard names the header, and two correlation values can disagree.
- Starlette's body-limit middleware, rejected at its probe; the kit's problem response remains.
- The library candidates evaluated in F4.4 and F4.7, each exempt after evaluation.
- AIP-193, 154, 155, 134, 160 and 122, where an RFC or a native mechanism already governs.
