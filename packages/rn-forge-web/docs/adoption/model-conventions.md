# Model conventions

**Normative for the ORM packages, advisory for applications. This page ships no
code, and that is deliberate.**

## Why there is no shared base class

There will never be a shared model base class or repository protocol across
Django and SQLAlchemy, and this page exists instead of one.

Django's ORM is active-record with a metaclass-driven declarative layer and a
global app registry; SQLAlchemy is data-mapper with a unit of work and explicit
sessions. They differ on transaction boundaries, lazy loading, the identity map
and migration generation — which is to say on everything a shared base class
would have to take a position on.

A shared *repository protocol* is worse than a shared base, not better: it
converges on a query API that is the intersection of two ORMs, which is an API
neither side's users will accept, and it acquires a new method every time an
application needs something the intersection lacks.

What *is* shared is the **vocabulary** each ORM's base class conforms to
without sharing code. Writing it down is what stops `rn_forge.django.BaseModel`
and a SQLAlchemy counterpart drifting into two dialects of the same
idea.

## Audit columns

Every persisted entity carries four:

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `created_by` | string identifier | yes | The principal's `subject` at creation. Null for rows created by a migration or a system process. |
| `create_time` | timestamp with time zone | no | Set once, on insert. Never updated. |
| `updated_by` | string identifier | yes | The principal's `subject` at the last write. Null under the same conditions as `created_by`. |
| `update_time` | timestamp with time zone | no | Set on insert and on every update. |

- **Times are UTC and timezone-aware.** A naive timestamp column is a bug that
  surfaces once a year.
- `create_time` equals `update_time` on a freshly inserted row rather than
  `update_time` being null. A null there forces every reader to write
  `update_time or create_time`.
- The actor is the `Principal.subject` from `rn_forge.web.auth`, so the audit
  trail names the caller the same way on every stack.

`rn-forge-django` uses the same names as database columns.
**That mapping is a Django-side detail and must not leak into this
vocabulary** — the Python names above are the contract, and a new SQLAlchemy
model uses ordinary snake_case columns.

## `status`

Every entity carries a `status` drawn from one shared enumeration:

| Value | Meaning |
| --- | --- |
| `ACTIVE` | The normal state. Visible and mutable. |
| `INACTIVE` | Retained and readable, excluded from normal listings, not mutable through ordinary endpoints. |
| `DELETED` | Soft-deleted. See below. |

An application that needs a domain lifecycle (`DRAFT`, `SUBMITTED`,
`APPROVED`, ...) models it as its **own** column. Overloading `status` with
domain states is how the shared vocabulary stops being shared.

## Optimistic concurrency

**This is the entry with teeth**, because `check_precondition` and both ORM
packages' versioned mixins depend on it.

- The column is named **`version`**.
- It is a monotonically increasing **`int`**, starting at 1 on insert.
- It is **bumped on every write**, by the ORM layer, not by the caller.
- A write that supplies a stale version fails; it does not silently win.

This is the only structural type this kit declares over a persisted object: a
`Versioned` thing has a primary key and an `int` `version`, and those are
exactly the two values `check_precondition` takes. Nothing beyond that pair is
shared.

## Natural keys

Both ORMs need a natural key for fixtures, and neither agrees on the spelling
by default.

- A model declares its natural key as an **ordered list of field names**, with
  dotted paths allowed for a key that reaches through a foreign key
  (`["code"]`, `["organisation.code", "code"]`).
- The list is unique together, and every field in it is non-nullable.
- The natural key is stable: it is what a fixture, a seed script and a
  cross-environment reference use, so a value in it is not something an
  ordinary update endpoint changes.
- A surrogate primary key still exists. A natural key is for *loading and
  referencing*, not for being the primary key.

## Soft delete and timestamps

**Deletion is a status transition, not a column.** A soft-deleted row has
`status = DELETED`; there is no separate `deleted_at` or `is_deleted`. Two
representations of the same fact drift, and the pair `is_deleted = false,
deleted_at = <a time>` is a state every codebase eventually finds in
production.

- `update_time` and `updated_by` record *when* and *by whom*, so a `deleted_at`
  adds nothing a soft delete needs.
- Default managers and default query scopes **exclude** `DELETED` rows.
  Retrieving them is explicit.
- A soft delete is reversible by a status transition, and that transition is an
  ordinary versioned write — it bumps `version` like any other.
- Hard deletion exists for data-retention compliance and is a deliberate,
  separately authorized operation, not the ordinary `DELETE` endpoint.
- A `DELETE` endpoint on an already-soft-deleted resource returns 404, per the
  API conventions.
