# Ideas

Ideas that are not yet agreed as pykit work. An entry has no ID and no status, and it does not authorize starting work. When the owner takes one up, it becomes a `New` epic or feature, its section moves into that file, and the entry is deleted. A dropped idea is deleted too.

[Back to the work index](index.md)

| Idea | Summary | Source |
| --- | --- | --- |
| [django-optional-areas](#django-optional-areas) | Decide whether Celery, fixtures and messaging stay in `rn-forge-django`. | Former E8, retired 2026-09-28 |
| [model-vocabulary](#model-vocabulary) | A shared model vocabulary, normative for both ORM packages: audit-column semantics, a shared `status` enumeration and natural-key rules. Waits for an application that needs one of these to behave the same on Django and SQLAlchemy. | F12.13, retired from E12 2026-09-29 |
| sqlalchemy-helpers | A SQLAlchemy `AsyncIdempotencyStore`, session and unit-of-work helpers, and readiness checks. Waits for a SQLAlchemy application to ask for them. | F12.5, retired from E12 2026-09-29 |
| cloudevents-envelope | A CloudEvents envelope builder. Waits for the outbox/inbox subsystem to need one. | F12.6, retired from E12 2026-09-29 |
| claim-check | The claim-check pattern for large messages. Waits for a second storage backend. | F12.7, retired from E12 2026-09-29 |
| django-cloud-messaging-adapters | Django cloud messaging adapters. Waits for a second cloud backend; depends on [django-optional-areas](#django-optional-areas) keeping messaging in `rn-forge-django`. | F12.10, retired from E12 2026-09-29 |
| product-installer-contract | A shared `ProductInstaller` contract. Shared installer mechanics stay in `rn-forge-tooling`: do not create `rn-forge-selfkit`. Waits for a second product that needs the same contract. | F12.8, retired from E12 2026-09-29 |
| [release-recovery-drill](#release-recovery-drill) | A live drill of tag-only release recovery. | S14.2.5, amended 2026-10-03 |
| [sonar-branch-analysis-plan](#sonar-branch-analysis-plan) | Decide whether to change the Sonar plan so branch dispatch can read its quality gate. | S14.4.2, amended 2026-10-03 |
| [full-local-sonar-scan](#full-local-sonar-scan) | Run the authorized full local Sonar scan. | S14.4.3, amended 2026-10-03 |

## django-optional-areas

`rn-forge-django` carries Celery, fixtures and messaging behind their own extras. For release-1 the owner kept all of them, and SAML, in the package (2026-09-26). SAML's placement is now part of [E13's design](epics/E13-auth/design.md#package-placement). The question left is whether the other three stay. A move after release-1 is a breaking version of `rn-forge-django`, because [ADR-0002](../adr/ADR-0002.md) forbids aliases.

## model-vocabulary

The [model conventions guide](../rn-forge-web/guides/model-conventions.md) describes what both ORM packages supply today and keeps the rest advisory, as the owner decided on 2026-09-25. These are the rules this entry would make normative for both packages; applications could still treat them as advice. The audit columns and `version` already exist in both packages. The `status` enumeration and natural keys are the new parts.

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

Soft delete is a nullable `delete_time` column, not a status, in AIP-164's shape, as [ADR-0010](../adr/ADR-0010.md) records. [F12.2](epics/E12-http-contract-extensions/F12.2-soft-delete.md) builds it.

## release-recovery-drill

Delete a package's latest GitHub Release while keeping its tag, rerun the original `main` push workflow, and confirm the release is recreated from the tag with its wheel and sdist and the tag still at its original commit; a second rerun must skip it. The local scenarios with real Git repositories and mocked `gh` cover the path. The drill is destructive and owner-run, so do it only if the added confidence is wanted.

## sonar-branch-analysis-plan

The organization's Sonar plan rejects reading non-main branch data, so a dispatched branch scan cannot read its quality gate. Pull request analysis works and is the validation route. Decide whether a plan change is worth it.

## full-local-sonar-scan

`.github/scripts/sonar_local.py` has a dry-run and mocked tests. The full authorized scan needs `sonar-scanner` installed and a `SONAR_TOKEN` from the owner; it has never been run.
