# rn-forge-django

Opinionated Django/DRF integration layer built on top of [`rn-forge-commons`](../rn-forge-commons). Part of
the [pykit](../../README.md) workspace.

## Install

```bash
uv add rn-forge-django
```

Optional extras:

| Extra | Adds |
| --- | --- |
| `drf` | Django REST Framework integration (views, serializers, exceptions), including Excel transfer support via `rn-forge-commons[excel]` |
| `jwt` | `drf` + `djangorestframework-simplejwt`-backed JWT auth |
| `saml` | `drf` + `djangorestframework-simplejwt` + `python3-saml` SAML auth support |
| `fixtures` | `rn-forge-commons[excel]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

## What's inside

- **`models`** — Abstract model base classes: `BaseModel` (status enum field, audit timestamps,
  natural-key fixture support via `NaturalKeyLookupManager`/`FixtureModelMixin`, opt-in
  `full_clean()`-on-save), `DateModel`, `DateRangeModel`, plus `TruncateModelMixin` for test teardown.
- **`auth`** — An installable Django app (`rn_forge.django.auth`, label `rn_forge_django_auth`) with
  sub-packages per mechanism: `auth.basic` (session login views), `auth.jwt` (JWT authentication,
  credentials, mixins, views), `auth.saml` (SAML login views), and `auth.drf` (shared DRF authentication
  classes, permissions, mixins, serializers).
- **`drf`** — DRF integration outside the auth app: `drf.views` (base view classes, bulk operations,
  Excel/transfer import-export, parsers/renderers), `drf.serializers` (base serializer + custom fields),
  `drf.exceptions` (maps package exceptions to DRF error responses).
- **`settings`** — `rn_forge_django_settings`: a typed, frozen-dataclass settings facade built from the
  Django `RN_FORGE_DJANGO` setting dict, auto-reloaded on `override_settings`/`setting_changed`.
- **`fixtures`** — Builds Django JSON fixtures from Excel workbooks (requires the `fixtures` extra).
- **`urls`** / **`views`** — Reusable standalone views and URLconf.

## Configuration

Settings are read from a single `RN_FORGE_DJANGO` dict in your Django settings module, e.g.:

```python
RN_FORGE_DJANGO = {
    "AUTH": {"SAML": {"SETTINGS": {...}, "RETURN_TO": "/"}},
    "DRF": {"VIEWS": {"DEFAULT_TRANSFER_FORMAT": "xlsx", "EXPORT_MAX_ROWS": 10_000}},
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
there is no separate Django settings module.
