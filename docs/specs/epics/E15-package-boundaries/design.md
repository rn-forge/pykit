# E15 — Package boundaries design

|  |  |
| -- | -- |
| **Epic** | [E15](index.md) |
| **Settled by** | [F15.1](F15.1-package-boundary-rule.md) |
| **Depends on** | [ADR-0002](../../../adr/ADR-0002.md), [ADR-0003](../../../adr/ADR-0003.md), [ADR-0004](../../../adr/ADR-0004.md), [ADR-0011](../../../adr/ADR-0011.md) |

Which parts of `rn-forge-commons` earn their own package, the one structure
every such package uses for its adapters, what moves into `rn-forge-auth` and
`rn-forge-data`, and which framework-neutral areas of `rn-forge-django` wait for
a trigger. [ADR-0011](../../../adr/ADR-0011.md) accepts the rule and the adapter
structure, and the owner answered the open questions on 2026-10-15.

[Back to E15](index.md)

## Problem

The problem in `rn-forge-commons` was its extras plumbing and its cohesion, not
its install size: nine extras, requested only by pykit's own packages and kiln,
and a chain of extras between the framework packages (`rn-forge-web[auth]` to
`rn-forge-django[oidc]` to `rn-forge-fastapi[oidc]`). The `resilience` extra has
no consumer, and the `excel` and `pandas` extras are requested by the framework
packages' transfer and fixtures extras. The moves below resolve this.

## Commons, module by module

Commons keeps `lang`, `fs`, `runtime`, `config`, `exceptions`, `findings`,
`logging` and its back-end extras, `lang/models`, `testing`, the dependency-free
`integration` protocols and `integration/resilience` (as an extra until it has a
consumer). `integration/auth` moves to `rn-forge-auth`, and `data/excel` and
`data/pandas` move to `rn-forge-data`.

## The rule

[ADR-0011](../../../adr/ADR-0011.md) records the decision: a part becomes a
package only when it has a distinct dependency set, a consumer today and one
audience, and the fixed cost of a package ([ADR-0004](../../../adr/ADR-0004.md))
is why a part that fails any test stays in commons.

## Adapter structure

[ADR-0011](../../../adr/ADR-0011.md) records the structure every package that
integrates with external systems takes: a core, adapters behind extras, a facade
that re-exports the core only, and framework packages that name
`rn-forge-<pkg>[<adapter>]`. A new package is useful only if the next adapter
does not force a refactor.

| Package | Core | Adapters (extra) |
| -- | -- | -- |
| `rn-forge-auth` | `Principal`, `Requirement`, the authentication and authorization protocols, the session store protocol, an in-memory store | `oidc` (PyJWT now; Authlib arrives with E13), later `redis` (a session store) |
| `rn-forge-data` | Workbook and row types, validation, `ColumnType` conversion | `pandas` |
| A future messaging core | Outbox and inbox store protocols, the relay and consumer loops | `django` and `sqlalchemy` stores |

A package with a single adapter still follows the shape. The first adapter is
where the shape is cheapest to get right.

## Today's map and target map

The package map after the split is in the
[workspace architecture](../../../architecture/workspace.md). Framework packages
name a package instead of a list of commons extras, so commons drops from nine
extras to six and loses its two heaviest dependency sets: pandas and the crypto
and JWT stack. `rn-forge-auth` depends on `rn-forge-web`, following
[E13's package placement](../E13-auth/design.md#package-placement).

## rn-forge-auth contents

[E13's package placement](../E13-auth/design.md#package-placement) decides why
auth is a separate package, and [F13.2](../E13-auth/F13.2-auth-package.md) moved
the token code, `Principal`, `Requirement` and `OidcAuthenticator` into it.
`rn-forge-web` kept the wire contract. Django's `jwt` extra and the simplejwt
flows are removed by E13, not E15.

## rn-forge-data contents

[F15.3](F15.3-data-package.md) moved the Excel and pandas code into
`rn-forge-data`: base dependencies `openpyxl` and `tablib[xlsx]`, and a `pandas`
extra, with `ExcelAdapter` in the `rn_forge.data.pandas` adapter so the core
never imports pandas. Commons lost its `excel` and `pandas` extras, and the
Django and FastAPI transfer and fixtures extras name `rn-forge-data`, which
fixed Django's undeclared openpyxl dependency.

## What a new package needs in this workspace

[Adding a package](../../../runbooks/adding-a-package.md) is the procedure for a
new workspace member.

## Consumers

Kiln builds the allowed rn-forge set from the archetype's list, the chosen
backend framework and, for lifecycle, tooling. The goldens are unaffected by
commons extras. A web golden picks up `rn-forge-auth` when it turns auth on and
`rn-forge-data` when it turns import and export on. Kiln follow-ups belong to
kiln's own backlog and, per [ADR-0008](../../../adr/ADR-0008.md), do not gate
pykit: allow `rn-forge-auth` and `rn-forge-data` in the web archetypes'
composition, and update kiln's `standard.md.j2` package description. The goldens
pin pykit to `@main`, not to the release tags that
[ADR-0004](../../../adr/ADR-0004.md) describes, which is fine for goldens that
track the pykit branch under test, but generated repositories need tags.

## Framework-neutral areas still in rn-forge-django

The real axis is the ORM, not the web framework. FastAPI has no ORM, and a
FastAPI application's persistence is `rn-forge-sqlalchemy` (async). None of
these areas belongs in `rn-forge-web`, which is the HTTP wire contract.

### Celery

`rn_forge.django.celery` is 43 lines. `RETRYABLE_TASK_KWARGS` is already
neutral. `make_app` is Django-specific only in its default
`config_source="django.conf:settings"` and its argument-less
`autodiscover_tasks()`. It could move to commons behind a `celery` extra, with a
FastAPI application passing its own config object and task packages. Feature:
[F15.7](F15.7-neutral-celery.md).

### Messaging

`rn_forge.django.messaging` is 251 lines: abstract outbox and inbox models,
`make_outbox_relay`, `process_event` and `UnknownMessageType`.

- **Neutral already, in commons:** `MessageBus`, `AsyncMessageBus`,
  `HandlerRegistry` and `InMemoryMessageBus`.
- **Could become neutral:** the relay loop (claim a batch, publish, mark, report
  lag, log), the consumer loop (dedupe, dispatch, record, re-raise),
  `UnknownMessageType` and the field vocabulary.
- **ORM-bound:** the models, `select_for_update(skip_locked=True)`,
  `transaction.atomic` and the database router.

Splitting needs `OutboxStore` and `InboxStore` protocols whose stores supply a
transaction scope, because the consumer must run the handler and record the
processed marker in one transaction. `rn-forge-sqlalchemy` would also need async
variants. Feature: [F15.5](F15.5-neutral-messaging.md).

### Fixtures

`rn_forge.django.fixtures` is 266 lines. The neutral half is workbook reading,
sheet and column validation, and the `ColumnType` enum with the conversions it
selects, which already call `PandasUtils`. That half belongs in `rn-forge-data`.
The Django half is the `loaddata` JSON output (`"app.model"`, `pk`, `fields`,
foreign keys as natural keys) and `load_data` (`django.setup` plus `loaddata`).
A SQLAlchemy loader needs natural-key rules that both ORMs share, which is the
[model-vocabulary](../../ideas/index.md#model-vocabulary) idea. Feature:
[F15.6](F15.6-neutral-fixtures.md).

### Decision

All three stay in `rn-forge-django` now. Each splits into a neutral core and ORM
bindings when its trigger fires. Moving messaging now is rejected because only
one binding exists to design against.

## Non-web consumers of the ORM packages

Real scenarios exist where the ORM packages run with no web server: a Celery
worker, an outbox relay process, fixture loading, an admin or data-migration
command, an ETL or batch job and a desktop SQLite tool. Django can also run
standalone through `settings.configure()` or `DJANGO_SETTINGS_MODULE` and
`django.setup()`.

Facts:

- `rn-forge-django`'s base dependencies include `rn-forge-web`, which brings
  pydantic and `opentelemetry-api`.
- The only model-layer import of web is `rn_forge.django.models.concurrency`
  (`VersionConflict`, `DomainConflict`), so importing `rn_forge.django.models`
  loads `rn_forge.web`. Every other web use in django is HTTP-facing: `drf/*`,
  `views.py`, `exceptions.py`, `cors.py`, `security.py` and `auth/drf/*`.
- `rn-forge-sqlalchemy`'s `concurrency.py` imports `VersionConflict`, which is a
  domain error. Its `pagination.py` uses web's page token, which is
  legitimately HTTP.

The cost today is two small extra installs and an import. Nothing is
functionally broken. The clean shape moves `VersionConflict` and
`DomainConflict` to commons as domain errors, with web keeping the mapping to
409 problems. Making web an extra of `rn-forge-django` is a further option; it
is breaking, and ADR-0002 forbids aliases. Both are deferred as
[F15.4](F15.4-domain-errors.md). If E13's placement work moves domain types out
of web, these two belong in the same move.

## Considered and rejected

- **`rn-forge-logging`.** Every package uses it, so it would be one more
  required dependency with no choice involved. Its back ends are already
  extras.
- **`rn-forge-integration` or `rn-forge-resilience`.** Nothing in pykit or kiln
  consumes resilience, and the protocols have no dependencies. A package would
  carry a tag and a pin for zero users.
- **`rn-forge-messaging` now.** The only implementation is Django's. Wait for
  the SQLAlchemy trigger, so the neutral core is designed against two real
  bindings.
- **`rn-forge-fs`, `rn-forge-lang`, `rn-forge-runtime`.** These are the
  foundation every package uses together. Splitting them multiplies pins
  without letting anyone install less.
- **`rn-forge-tabular` as the name for the data package.** The owner chose
  `rn-forge-data` on 2026-10-13.

## Answered questions

The owner answered these on 2026-10-15, in
[S15.1.1](F15.1-package-boundary-rule.md).

- **`rn-forge-data` base dependencies or extras?** openpyxl and tablib in the
  base, pandas behind the `pandas` extra. Excel is the package's purpose and
  pandas is heavy. If the package grows into data-science utilities, pandas
  can move into the base in a later breaking release.
- **Is `rn-forge-auth`'s JWT verification core or the `oidc` extra?** The `oidc`
  extra, so the core stays dependency-free and follows the adapter structure.
- **Order of F13.2 and E13's adapter features.** F13.2 first, after
  [F13.1](../E13-auth/F13.1-auth-design.md) settles placement, so the adapters
  are written inside the package.
- **Does F15.4 join release 6 if E13 already reshapes web?** Yes in that case,
  as one move. Otherwise it stays deferred.
- **Package versions.** `0.1.0` for the new packages, and breaking bumps for
  commons, web, django and fastapi.
