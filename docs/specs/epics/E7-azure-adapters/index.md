# E7 — Azure adapters

This epic retains the Azure package proposal until its owner schedules it. No Azure package scaffold or release assignment exists.

**Status:** deferred

**Readiness:** not ready

**Readiness basis:** Namespace, service gates and Entra scope remain unresolved; see Open questions.

**Owner:** pykit owner.

**Entry criteria:** Owner schedules the package and settles its namespace. Service Bus and Azure Monitor need their original gates before implementation.

[Back to the work index](../../index.md)

| Source item | Entry criterion and disposition |
| --- | --- |
| Azure Phases 0–3 | Commons protocols are ready; package scheduling and namespace remain open. |
| Phase 4, Service Bus | Real adopter, protocol and test strategy must pass the gate. |
| Phase 5, Azure Monitor | Real consumer and a useful export boundary must pass the gate. |
| Azure OpenAI | Second LLM supplier prompts a separate package decision. |
| Azure DevOps | Keep generic mechanics in commons; revisit with a concrete adapter need. |
| Managed-identity PostgreSQL | Revisit when a deployment forbids passwords. |
| Blob-lease `LockPort` | Revisit on a multi-host need, with the port redesigned first. |
| Entra OIDC | The source plan records a generic OIDC recipe rather than an auth adapter. Confirm scope before any build. |

**Source:** `azure-library-plan.md`, Phases 0–5 and Deferred. The [ledger](../../../plans/context.md) preserves the gates and the source-versus-register Entra conflict. [ADR-0006](../../../adr/ADR-0006.md) governs optional integration boundaries.

## Open questions

Which namespace will the package use? Do the Service Bus and Azure Monitor proposals satisfy their consumer and test gates? Is Entra scope only an OIDC recipe or an adapter? Settle each before its affected implementation.
