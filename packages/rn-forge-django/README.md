# rn-forge-django

Opinionated Django/DRF integration layer built on top of [`rn-forge-commons`](../rn-forge-commons)
and [`rn-forge-web`](../rn-forge-web). Part of the [pykit](../../README.md) workspace.

## Install

Not on PyPI; a release is a git tag. Declare a pinned direct URL:

```bash
uv add "rn-forge-django[all] @ git+https://github.com/rn-forge/pykit@rn-forge-django-v0.3.0#subdirectory=packages/rn-forge-django"
```

Optional extras:

| Extra | Adds |
| --- | --- |
| `drf` | Django REST Framework integration (views, serializers, exceptions, pagination, idempotency, concurrency, casing), including Excel transfer support via `rn-forge-commons[excel]` |
| `jwt` | `djangorestframework-simplejwt`-backed JWT auth — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `saml` | `djangorestframework-simplejwt` + `python3-saml` SAML auth support — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `openapi` | `drf-spectacular`, for `drf.openapi` — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `oidc` | `rn-forge-commons[auth]` (`pyjwt[crypto]`), for `auth.drf.oidc` JWKS bearer auth — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `celery` | `celery`, for the `celery` app factory |
| `fixtures` | `rn-forge-commons[excel]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

## What's inside

- **`models`** — Abstract model base classes: `BaseModel` (status enum field, audit timestamps,
  natural-key fixture support via `NaturalKeyLookupManager`/`FixtureModelMixin`, opt-in
  `full_clean()`-on-save), `DateModel`, `DateRangeModel`, `TruncateModelMixin`; the opt-in
  `VersionedModelMixin`/`ImmutableModelMixin`; and `SequenceGenerator` over an abstract counter.
- **`auth`** — An installable Django app (`rn_forge.django.auth`, label `rn_forge_django_auth`) with
  sub-packages per mechanism: `auth.basic` (session login views), `auth.jwt` (JWT authentication,
  credentials, mixins, views), `auth.saml` (SAML login views), and `auth.drf` (shared DRF authentication
  classes, permissions, mixins, serializers, and the `rn_forge.web` principal binding for externally
  issued bearer tokens).
- **`drf`** — DRF integration outside the auth app: `drf.views` (base view classes, bulk operations,
  Excel/transfer import-export, parsers/renderers, `PermissionByMethodMixin`), `drf.serializers` (base
  serializer, custom fields, wire mirrors), `drf.exceptions` (the RFC 9457 problem handler and the
  legacy handler), `drf.pagination` (AIP-158 cursor pagination), `drf.idempotency`, `drf.concurrency`,
  `drf.casing` (camelCase renderer/parser) and `drf.openapi` (drf-spectacular; `openapi` extra).
- **`middleware`** — the WSGI access-log middleware.
- **`tracing`** (`otel` extra) — `instrument()`: OpenTelemetry instrumentation for Django, called once
  before Django loads.
- **`messaging`** — transactional outbox/inbox: abstract models, `make_outbox_relay`, `process_event`
  (bus and handler registry come from `rn_forge.commons.integration.messaging`).
- **`celery`** (`celery` extra) — `make_app` and `RETRYABLE_TASK_KWARGS`.
- **`settings`** — `rn_forge_django_settings`: a typed, frozen-dataclass settings facade built from the
  Django `RN_FORGE_DJANGO` setting dict, auto-reloaded on `override_settings`/`setting_changed`.
- **`fixtures`** — Builds Django JSON fixtures from Excel workbooks (requires the `fixtures` extra).
- **`urls`** / **`views`** — Reusable standalone views (including the `readiness_view` factory) and
  URLconf; `utils` carries the `require_settings`/`require_environment` startup guards.

The HTTP wire semantics — problem bodies, preconditions, pagination tokens, idempotency keys,
readiness reports, the auth contract — are `rn-forge-web`'s. Everything here that touches them is an
adapter, and `tests/test_conformance.py` drives the shared conformance table through a Django
application wired from them.

## Dependencies and why

- **`rn-forge-web`** is a base dependency: five modules are adapters over it.
- **`drf-spectacular`** (`openapi` extra) — maintained, supports Django 6.0 and DRF 3.17.
- **`djangorestframework-camel-case` was evaluated and not taken** — last release 1.4.2 (2023-02),
  classifiers stop at Python 3.10. `drf.casing` replaces it.
- **`oidc` extra** — JWKS verification is `rn-forge-commons[auth]` (PyJWT); `auth.drf.oidc` only
  binds it to DRF. It is separate from `jwt` so JWKS auth does not install simplejwt.
- **`celery` extra** — Celery 5.6.3; its classifiers stop at 3.13, but it imports and runs on 3.14
  (checked 2026-09-12, and by `tests/test_celery.py`).
- **No migrations.** `SequenceGenerator`'s counter is abstract, so installing this package adds no
  tables.

## Configuration

Settings are read from a single `RN_FORGE_DJANGO` dict in your Django settings module, e.g.:

```python
RN_FORGE_DJANGO = {
    "AUTH": {"SAML": {"SETTINGS": {...}, "RETURN_TO": "/"}},
    "DRF": {
        "VIEWS": {"DEFAULT_TRANSFER_FORMAT": "xlsx", "EXPORT_MAX_ROWS": 10_000},
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

Tests configure Django directly in [`tests/conftest.py`](tests/conftest.py) (sqlite in-memory database) —
there is no separate Django settings module. Test-only models and their tables follow the convention
in that file's docstring.
