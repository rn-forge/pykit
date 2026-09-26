# E7 — Azure adapters

**Status:** deferred · **Owner:** pykit

A proposed `rn-forge-azure` package implementing commons' secret, object-store and messaging protocols over Azure services. No package scaffold exists.

**Entry criteria:** the owner schedules the package and settles its namespace. Do not start or elaborate this epic unless asked.

[Back to the work index](../../index.md)

| ID | Item | Entry criterion and disposition |
| --- | --- | --- |
| F7.1 | Package scaffold, credentials, Key Vault and Blob adapters (Azure Phases 0–3) | Commons protocols are ready; scheduling and namespace are open. |
| F7.2 | Service Bus `MessageBus` adapter (Phase 4) | A real adopter, the protocol and a test strategy must pass the Phase 4.1 gate. |
| F7.3 | Azure Monitor export (Phase 5) | A real consumer and a useful export boundary must pass the Phase 5.1 gate. |
| F7.4 | Azure OpenAI | A second LLM supplier prompts a separate package decision. |
| F7.5 | Azure DevOps | Generic mechanics stay in commons; revisit with a concrete adapter need. |
| F7.6 | Managed-identity PostgreSQL | A deployment forbids passwords. |
| F7.7 | Blob-lease `LockPort` | A multi-host need, with the port redesigned first. |
| F7.8 | Entra ID auth | The source plan records a generic OIDC recipe, not an adapter. Confirm scope before any build. |

**Source:** `plans/archive/azure-library-plan.md`, Phases 0–5 and "Deferred — do not build these yet". The [ledger](../../../plans/context.md) keeps the gates and the conflict over F7.8's scope. [ADR-0002](../../../adr/ADR-0002.md) puts the protocols in commons; [ADR-0003](../../../adr/ADR-0003.md) governs optional integrations.

## Open questions

- Which namespace will the package use?
- Do F7.2 and F7.3 pass their consumer and test gates?
- Is F7.8 only an OIDC recipe, or an adapter?
