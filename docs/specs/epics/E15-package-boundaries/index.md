# E15 — Package boundaries

| | |
| --- | --- |
| **State** | Active |
| **Start Date** | 2026-10-15 |

Split framework-neutral areas out of `rn-forge-commons` into purpose-named packages, only when they pass the three-test rule of [ADR-0011](../../../adr/ADR-0011.md), and give every such package one adapter structure. A new adapter (an auth provider, a file format, a message store, an ORM) is then a module plus an extra, with no refactor of the core. `rn-forge-auth` and `rn-forge-data` qualify now. The messaging, fixtures and Celery areas of `rn-forge-django`, and the web dependency of the ORM packages, are deferred until a trigger fires.

[The design](design.md) holds the evidence, the adapter structure and the package contents. [ADR-0011](../../../adr/ADR-0011.md) records the rule and the adapter structure.

E15 and [E13](../E13-auth/index.md) divide the auth work. E15 creates the `rn-forge-auth` package and moves existing code into it. E13 owns new auth behaviour: the adapters, the session and HTTP surface, authorization policy and the removal of the locally issued JWT flows. New adapter implementations are deliberately outside E15.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| --- | --- | --- |
| [F15.1 — Package boundary rule](F15.1-package-boundary-rule.md) | Decide the three-test rule and the adapter structure, and enforce the structure with import contracts. | Active |
| [F15.2 — rn-forge-auth package](F15.2-auth-package.md) | Create the package and move the existing token, `Principal` and OIDC code into it. | New |
| [F15.3 — rn-forge-data package](F15.3-data-package.md) | Create the package and move the Excel and pandas code into it. | New |
| [F15.4 — Domain errors in commons](F15.4-domain-errors.md) | Move `VersionConflict` and `DomainConflict` to commons so the ORM packages need no web import. | New |
| [F15.5 — Framework-neutral messaging core](F15.5-neutral-messaging.md) | Split the outbox and inbox loops from their Django models. | New |
| [F15.6 — Framework-neutral fixtures](F15.6-neutral-fixtures.md) | Split workbook reading and validation from Django's `loaddata` output. | New |
| [F15.7 — Framework-neutral Celery app factory](F15.7-neutral-celery.md) | Make the Celery app factory usable without Django. | New |

F15.4 to F15.7 are tagged `deferred`. Do not start them unless the owner asks.

Governing decision: [ADR-0011](../../../adr/ADR-0011.md). Related: [ADR-0002](../../../adr/ADR-0002.md) (no aliases), [ADR-0003](../../../adr/ADR-0003.md) (extras and the facade), [ADR-0004](../../../adr/ADR-0004.md) (pinned tags).

## Considered and rejected

- A broad split of commons. Its base install is five small libraries, and a split removes no install weight.
- `rn-forge-logging`, `rn-forge-integration` or `rn-forge-resilience`, `rn-forge-messaging` now, and `rn-forge-fs`, `-lang` or `-runtime`. The [design](design.md#considered-and-rejected) gives the reason for each.

## Answered questions

The owner answered the design's questions on 2026-10-15 in [S15.1.1](F15.1-package-boundary-rule.md). The [design](design.md#answered-questions) records the answers.
