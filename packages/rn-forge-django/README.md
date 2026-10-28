# rn-forge-django

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-django/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-django/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-django)
· [All pykit packages](https://rn-forge.github.io/pykit/)

Opinionated Django/DRF integration layer built on top of
[`rn-forge-commons`](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-commons)
and
[`rn-forge-web`](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-web).

## Install

Not on PyPI; a release is a git tag. Declare pykit's package index and require
the package by version range, or pin a tag by direct URL:

```bash
uv add "rn-forge-django[all] @ git+https://github.com/rn-forge/pykit@rn-forge-django-v0.5.0#subdirectory=packages/rn-forge-django"
```

Application code imports `rn_forge.web` directly (wire models, pagination,
problem types, the auth contract), and this package does not re-export it.
Declare `rn-forge-web` as well, so the import is not an undeclared transitive
dependency:

```bash
uv add "rn-forge-web @ git+https://github.com/rn-forge/pykit@rn-forge-web-v0.2.0#subdirectory=packages/rn-forge-web"
```

Optional extras:

| Extra | Adds |
| -- | -- |
| `drf` | Django REST Framework integration (views, serializers, exceptions, pagination, idempotency, concurrency, casing) |
| `transfer` | `django-import-export` + `rn-forge-data` (`tablib`, `openpyxl`), for `rn_forge.django.drf.transfer`: tabular export and import, batch create and delete |
| `openapi` | `drf-spectacular`, for `drf.openapi` |
| `oidc` | `rn-forge-auth[oidc]` (`pyjwt[crypto]`), for `auth.drf.oidc` JWKS bearer auth |
| `redis` | `rn-forge-auth[redis]`, the Redis client for Django's Redis cache backend that holds login transactions and revoked session IDs |
| `celery` | `celery`, for the `celery` app factory |
| `fixtures` | `rn-forge-data[pandas]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

## What's inside

- **`models`** — Abstract model base classes: `BaseModel` (status enum field,
  audit timestamps, natural-key fixture support via
  `NaturalKeyLookupManager`/`FixtureModelMixin`, opt-in
  `full_clean()`-on-save), `DateModel`, `DateRangeModel`,
  `TruncateModelMixin`; the opt-in `VersionedModelMixin`/`ImmutableModelMixin`;
  and `SequenceGenerator` over an abstract counter.
- **`auth`** — An installable Django app (`rn_forge.django.auth`, label
  `rn_forge_django_auth`) that binds `rn-forge-auth` to Django and DRF:
  `routes` (the `/auth` URLconf and its configuration), `sessions`
  (`django.contrib.sessions` sessions with timeouts and revocation), `csrf`
  (CSRF middleware and settings), `stores` (login transactions and replay
  records in Django's cache), `rate_limit`, `audit` (audit events),
  `accounts` and `models` (the default account resolver and its link and state
  tables), `authorization` (the default authorization context provider), and
  `auth.drf` (session and bearer authentication, permission-key and
  resource-policy hooks, serializers and the management viewsets).
- **`drf`** — DRF integration outside the auth app: `drf.views` (base view
  classes, mixins, `PermissionByMethodMixin`), `drf.routers`
  (`CustomMethodRouter`, AIP-136 colon custom methods), `drf.transfer`
  (`transfer` extra: tabular export/import, batch create/delete),
  `drf.serializers` (base serializer, custom fields), `drf.exceptions` (the
  RFC 9457 problem handler and the legacy handler), `drf.pagination` (AIP-158
  cursor pagination), `drf.idempotency`, `drf.concurrency`, `drf.casing`
  (camelCase renderer/parser) and `drf.openapi` (drf-spectacular; `openapi`
  extra).
- **`tracing`** (`otel` extra) — `instrument()`: OpenTelemetry instrumentation
  for Django, called once before Django loads.
- **`messaging`** — transactional outbox/inbox: abstract models,
  `make_outbox_relay`, `process_event` (bus and handler registry come from
  `rn_forge.commons.integration.messaging`).
- **`celery`** (`celery` extra) — `make_app` and `RETRYABLE_TASK_KWARGS`.
- **`settings`** — `rn_forge_django_settings`: a typed, frozen-dataclass
  settings facade built from the Django `RN_FORGE_DJANGO` setting dict,
  auto-reloaded on `override_settings`/`setting_changed`.
- **`fixtures`** — Builds Django JSON fixtures from Excel workbooks (requires
  the `fixtures` extra).
- **`urls`** / **`views`** — Reusable standalone views (including the
  `readiness_view` factory and `debug_request`) and URLconf; `utils` carries
  the `require_settings`/`require_environment` startup guards.

The HTTP wire semantics — problem bodies, preconditions, pagination tokens,
idempotency keys, readiness reports, the auth contract — are `rn-forge-web`'s.
Everything here that touches them is an adapter, and `tests/test_conformance.py`
drives the shared conformance table through a Django application wired from
them.

## Dependencies and package behavior

- **`rn-forge-web`** is a base dependency: five modules are adapters over it.
- **`rn-forge-auth`** is a base dependency: `auth` binds its login flows,
  stores, `Principal`, `Requirement` and authorization contracts to Django and
  DRF.
- **`drf-spectacular`** (`openapi` extra) supplies the OpenAPI schema
  integration.
- **`drf.casing`** supplies the camelCase renderer and parser.
- **`oidc` extra** — JWKS verification is `rn-forge-auth[oidc]` (PyJWT);
  `auth.drf.oidc` only binds it to DRF.
- **`celery` extra** — supplies the Celery app factory.
- **Migrations.** The auth app has one, for the external-account link and
  account-state tables. `SequenceGenerator`'s counter is abstract and adds no
  table.

## Configuration

Settings are read from a single `RN_FORGE_DJANGO` dict in your Django settings
module, e.g.:

```python
RN_FORGE_DJANGO = {
    "AUTH": {"PROBLEM_TYPE_BASE": "https://errors.example.com/"},
    "DRF": {
        "TRANSFER": {"MAX_ROWS": 10_000},
        "PAGINATION": {"PAGE_SIZE": 50, "MAX_PAGE_SIZE": 200},
        "CASING": {"ENABLED": True},
    },
}
```

To use the bundled auth app, add `"rn_forge.django.auth"` to `INSTALLED_APPS`.

## Development

From the repo root or this directory:

```bash
uv run pytest packages/rn-forge-django             # all tests
uv run pytest packages/rn-forge-django -m unit      # fast isolated tests
uv run pytest packages/rn-forge-django -m integration  # database-backed tests
uv run ruff check packages/rn-forge-django
uv run pyright
```

Tests configure Django directly in
[`tests/conftest.py`](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-django/tests/conftest.py)
(sqlite in-memory database) — there is no separate Django settings module.
Test-only models and their tables follow the convention in that file's
docstring.
