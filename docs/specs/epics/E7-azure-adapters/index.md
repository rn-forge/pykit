# E7 — Azure adapters

**Status:** deferred

A proposed `rn-forge-azure` package implementing commons' secret, object-store and messaging protocols over Azure services. No package scaffold exists.

**Entry criteria:** the owner schedules the package and settles its namespace. Do not start or elaborate this epic unless asked.

[Back to the work index](../../index.md)

| ID | Item | Entry criterion and disposition |
| --- | --- | --- |
| F7.1 | Package scaffold, credentials, Key Vault and Blob adapters | Commons protocols are ready; scheduling and namespace are open. |
| F7.2 | Service Bus `MessageBus` adapter | A real adopter, the protocol and a test strategy must all be in place. |
| F7.3 | Azure Monitor export | A real consumer and a useful export boundary must both be in place. |
| F7.4 | Azure OpenAI | A second LLM supplier prompts a separate package decision. |
| F7.5 | Azure DevOps | Generic mechanics stay in commons; revisit with a concrete adapter need. |
| F7.6 | Managed-identity PostgreSQL | A deployment forbids passwords. |
| F7.7 | Blob-lease `LockPort` | A multi-host need, with the port redesigned first. |
| F7.8 | Entra ID auth | Scoped so far as a generic OIDC recipe, not an adapter. Confirm scope before any build. |

[ADR-0002](../../../adr/ADR-0002.md) puts the protocols in commons; [ADR-0003](../../../adr/ADR-0003.md) governs optional integrations.

## Open questions

- Which namespace will the package use?
- Do F7.2 and F7.3 have their consumers and test strategies?
- Is F7.8 only an OIDC recipe, or an adapter?
