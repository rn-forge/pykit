# E12 — On-demand features

**Status:** deferred

Proposals that wait for a named consumer. Each has a trigger; when it fires, the item gets its own feature file with stories and acceptance before any code.

**Entry criteria:** the row's trigger occurs.

[Back to the work index](../../index.md)

| ID | Proposal | Trigger |
| --- | --- | --- |
| F12.1 | `:batchGet` and `:batchUpdate` handlers; the spelling is already documented | A consumer needs the handlers. |
| F12.2 | Soft delete in AIP-164's shape: `deleteTime`, `:undelete`, `showDeleted`. Conflicts with the status-based soft delete in F12.13; whichever is promoted first settles the other. | A consumer needs soft delete on the wire. |
| F12.3 | Multi-column sorting, with composite keysets and NULL ordering | The owner starts the ideation. |
| F12.4 | Multi-tenant row scoping | A second application states its tenancy model. |
| F12.5 | SQLAlchemy `AsyncIdempotencyStore`, session and unit-of-work helpers, readiness checks | A SQLAlchemy application asks for them. |
| F12.6 | CloudEvents envelope builder | The outbox/inbox subsystem needs one. |
| F12.7 | Claim-check pattern | A second storage backend is in view. |
| F12.8 | A shared `ProductInstaller` contract. Shared installer mechanics stay in `rn-forge-tooling`: do not create `rn-forge-selfkit`. | A second product needs the same contract. |
| F12.9 | AIP-157 `readMask` partial responses | Payload size makes partial responses necessary. |
| F12.10 | Django cloud messaging adapters | A second cloud backend needs an adapter. |
| F12.11 | Django `AUTH.OIDC` settings block | A second consumer needs OIDC configuration through the settings facade. |
| F12.12 | Fix the Django `RequestUtils` name collision | A breaking-change plan is approved. |
| F12.13 | A shared model vocabulary for SQLAlchemy: audit-column semantics, a shared `status` enumeration, natural-key rules and status-based soft delete, normative for both ORM packages | An application needs one of these to behave the same on Django and SQLAlchemy. |

## F12.13 — The proposed model vocabulary

The [model conventions guide](../../../rn-forge-web/guides/model-conventions.md) describes what both ORM packages supply today and keeps the rest advisory, as the owner decided on 2026-09-25. These are the rules F12.13 would make normative for both packages; applications could still treat them as advice. The audit columns and `version` already exist in both packages. The `status` enumeration, natural keys and soft delete are the new parts.

There is no shared model base class or repository protocol. Django's ORM is active-record and SQLAlchemy's is data-mapper, so they differ on transactions, lazy loading, the identity map and migrations. A shared protocol would shrink to what both query APIs have in common. What is shared is a vocabulary that each package's base class follows without sharing code.

### Audit columns

Every persisted entity carries four:

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `created_by` | string identifier | yes | The principal's `subject` at creation. Null for rows created by a migration or a system process. |
| `create_time` | timestamp with time zone | no | Set once, on insert. Never updated. |
| `updated_by` | string identifier | yes | The principal's `subject` at the last write. Null under the same conditions as `created_by`. |
| `update_time` | timestamp with time zone | no | Set on insert and on every update. |

- Times are UTC and timezone-aware.
- On a freshly inserted row, `update_time` equals `create_time`; it is never null.
- The actor is the `Principal.subject` from `rn_forge.web.auth`, so the audit trail names the caller the same way on every stack.
- The Python names above are the contract. How one package maps them to database columns does not leak into the vocabulary.

### `status`

Every entity carries a `status` drawn from one shared enumeration:

| Value | Meaning |
| --- | --- |
| `ACTIVE` | The normal state. Visible and mutable. |
| `INACTIVE` | Retained and readable, excluded from normal listings, not mutable through ordinary endpoints. |
| `DELETED` | Soft-deleted; see below. |

An application that needs a domain lifecycle (`DRAFT`, `SUBMITTED`, `APPROVED`, …) models it as its own column and does not overload `status`. Django's `Status` has five values today (`Active`, `Inactive`, `Error`, `Deleted`, `Expired`), so adopting this enumeration changes it.

### Optimistic concurrency

- The column is named `version`.
- It is a monotonically increasing `int`, starting at 1 on insert.
- The ORM layer bumps it on every write; the caller never does.
- A write that supplies a stale version fails; it does not silently win.

This is the only structural type declared over a persisted object: a `Versioned` thing has a primary key and an `int` `version`, exactly the two values `check_precondition` takes.

### Natural keys

- A model declares its natural key as an ordered list of field names. Dotted paths reach through a foreign key: `["code"]`, `["organisation.code", "code"]`.
- The fields are unique together, and every one is non-nullable.
- The natural key is stable: fixtures, seed scripts and cross-environment references use it, so an ordinary update endpoint does not change it.
- A surrogate primary key still exists. The natural key is for loading and referencing, not for being the primary key.

### Soft delete

- Deletion is a status transition, not a column: a soft-deleted row has `status = DELETED`, with no `deleted_at` or `is_deleted`. `update_time` and `updated_by` record when and by whom.
- Default managers and query scopes exclude `DELETED` rows; retrieving them is explicit.
- A soft delete is reversed by a status transition, which is an ordinary versioned write and bumps `version`.
- Hard deletion exists for data-retention compliance and is a separately authorized operation, not the ordinary `DELETE` endpoint.
- A `DELETE` on a resource that is already soft-deleted returns 404, per the API conventions.

F12.2's AIP-164 shape (`deleteTime`, `:undelete`, `showDeleted`) conflicts with this section. Whichever is promoted first settles the other.
