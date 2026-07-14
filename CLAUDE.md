# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

`pykit` is a uv workspace containing a family of `rn-forge-*` Python packages. It is a personal dev-kit,
not a deployable app.

- **`packages/rn-forge-commons`** (import path `rn_forge.commons`, module name `rn_forge.commons`) — general
  Python utilities with no Django dependency: config loading (`config.py`), collections/dict/json/yaml
  helpers (`collections.py`), structured logging built on `verboselogs`/`coloredlogs` (`logging.py`),
  dataclass mixins, subprocess/task helpers, Excel/pandas helpers (optional extras), CLI argument parsing
  (`console.py`). `src/rn_forge/commons/__init__.py` is the curated public API — re-export new symbols there
  when adding public functionality.
- **`packages/rn-forge-django`** (import path `rn_forge.django`) — Django/DRF integration layer built on top
  of `rn-forge-commons`. Depends on `rn-forge-commons` via `[tool.uv.sources]` workspace linking (not PyPI).
  Optional extras: `drf` (djangorestframework, plus `rn-forge-commons[excel]` since `drf.views` eagerly
  imports the Excel renderer/parser), `jwt` (`drf` + djangorestframework-simplejwt), `saml` (`drf` +
  djangorestframework-simplejwt + python3-saml), `fixtures` (`rn-forge-commons[excel]`), `all` (everything
  above).

Both packages use `uv_build` as the build backend with `module-name` mapped to their `rn_forge.*` namespace
package, and both ship a `py.typed` marker (strict typing is a contract of these libraries).

## Commands

Run all commands from the repo root unless testing a single package.

```bash
uv sync --all-extras                     # install workspace + all optional extras
uv run pytest                            # run tests across the workspace
uv run pytest packages/rn-forge-django   # run one package's tests
uv run pytest -k test_name                # run a single test by name/keyword
uv run pytest -m unit                     # rn-forge-django only: fast isolated tests
uv run pytest -m integration              # rn-forge-django only: DB-backed tests
uv run ruff check .                       # lint
uv run ruff format .                      # format
uv run pyright                            # type check (strict mode, see below)
```

Per-package commands work the same way with `--directory packages/<pkg>` or by `cd`-ing into the package
first (each package has its own `pyproject.toml`/`dev` dependency group). Each package's `dev`/`docs`
dependency groups self-reference their own `all` (django) / `excel` (commons) extra — e.g.
`dev = ["rn-forge-django[all]", "assertpy>=1.1", ...]` — so a `--group dev` sync always exercises every
optional code path instead of silently skipping `pytest.importorskip`-gated tests.

### Type checking scope

Root `pyproject.toml` configures Pyright in `strict` mode, `include = ["packages"]`, `ignore = ["tests",
"**/tests"]`. Test code is intentionally excluded from strict typing; library source under `src/` is not —
new source code must satisfy strict mode (explicit types, no untyped `Any` leakage across public APIs).

### Docs

`rn-forge-commons` has an mkdocs site (`packages/rn-forge-commons/mkdocs.yml`, `docs/` dir, `mkdocstrings`
autogenerating API docs from docstrings under `src`). Build with `uv run --group docs mkdocs build` from
that package directory. Keep docstrings accurate since they are the doc source, not just IDE hints.

## Architecture notes

### Settings facade pattern (rn-forge-django)

`rn_forge/django/settings.py` exposes a single module-level `rn_forge_django_settings` instance (a frozen
dataclass tree: `RnforgeDjangoSettings` → `AuthSettings`/`DRFSettings` → nested settings). It is built once
from the Django `RN_FORGE_DJANGO` setting dict and rebuilt automatically via a `setting_changed` signal
handler (`_reload_settings`), which matters for tests using `override_settings`. When adding a new
configurable option: add a `TypedDict` field to the relevant `*SettingsDict`, a field on the matching
frozen dataclass, and wire extraction in `_build_settings()` using `DictUtils.get`/`_get_mapping` for
nested path lookups (e.g. `"DRF.VIEWS"`).

### Model base classes (rn_forge.django.models)

`models/base.py` defines the abstract model hierarchy nearly all concrete models should build on:

- `BaseModel` — adds `status` (`EnumField` over `Status` enum), `created_by`/`created_at`/`updated_by`/
  `updated_at` audit columns (DB columns are camelCase for legacy compatibility, Python fields are
  snake_case), a `NaturalKeyLookupManager` default manager, `TruncateModelMixin`, and `FixtureModelMixin`.
- `DateModel` / `DateRangeModel` — extend `BaseModel` with date/date-range fields.
- Validation-on-save is opt-in: set `validate_on_save = True` on a model to have `save()` call
  `full_clean()` automatically; `get_full_clean_exclude()` controls which fields are excluded when a
  partial `update_fields` save is used.
- Natural-key fixture loading: implement `natural_keys()` (list of field names, dotted paths allowed) on
  a model to get `get_by_natural_key()`/`natural_key()` support for Django fixtures.

### Auth package (rn_forge.django.auth)

Sub-namespaced by auth mechanism: `auth/basic`, `auth/jwt`, `auth/saml`, plus shared `auth/drf` (DRF
authentication classes, permissions, mixins, serializers) and `auth/credentials.py`/`auth/payload.py` for
the common credential/payload shapes. The app is registered under the stable label `rn_forge_django_auth`
(`auth/apps.py`) so fixtures/migrations/admin registration have a fixed reference point independent of the
Python import path.

### DRF integration (rn_forge.django.drf)

`drf/views/` provides base view classes and mixins (`base.py`, `mixins.py`, `bulk.py`) plus transfer/export
helpers (`excel.py`, `transfer.py`, `parsers.py`, `renderers.py`) — these read `DRFViewsSettings` from the
settings facade above (transfer format, row limits, permission-action map). `drf/serializers/` provides a
`base.py` serializer and custom `fields.py`. `drf/exceptions.py` maps this package's exceptions to DRF
error responses.

## Testing conventions

- Tests live in each package's `tests/`, mirroring the `src/rn_forge/<pkg>/` layout (e.g.
  `tests/auth/drf/test_authentication_and_permissions.py` tests `src/rn_forge/django/auth/drf/`).
- `rn-forge-django/tests/conftest.py` configures Django (`settings.configure(...)`, sqlite in-memory DB,
  `django.setup()`) — no separate Django settings module exists; this conftest is the only settings source
  for tests.
- `rn-forge-django` defines `unit` and `integration` pytest markers (`pyproject.toml`) — mark DB-backed
  tests `integration` and fast isolated tests `unit`.
- `pytest-randomly` randomizes test order by default in both packages — do not rely on cross-test ordering.
- Tests are excluded from ruff's lint rules (`per-file-ignores` = `ALL` for `**/tests/*`) and from Pyright's
  strict checking.
