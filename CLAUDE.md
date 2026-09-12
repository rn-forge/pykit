# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here in a new session

`docs/plans/commons-upgrade-plan.md` is the record of how this workspace got its
current shape. Parts A–C are committed; Part D — the three-layer split into
`rn-forge-commons`, `rn-forge-cli` and `rn-forge-tooling`, the re-layout of all
of them, and the Phase C review findings — is applied in the working tree, with
its checklist in that document marking what is done and what is left. The
decisions behind it are in `../kiln` (ADR-0002, ADR-0005, ADR-0009; plan §0.8,
§2.8, §2.11 and Phase C.2).

The "Repository overview" below describes the tree as it now is.

## Repository overview

`pykit` is a uv workspace containing a family of `rn-forge-*` Python packages. It is a personal dev-kit, not a deployable app.

- **`packages/rn-forge-commons`** (import path `rn_forge.commons`) — runtime-neutral Python
    utilities with no web-framework dependency, grouped by kind of mechanism rather than laid out
    flat. Top level: config loading (`config.py`), `AppException` (`exceptions.py`), structured
    check results (`findings.py`), pytest helpers (`testing.py`). `lang/` — nested dict/list
    helpers (`collections.py`), dataclass mixins backed by `dacite` (`dataclasses.py`),
    `reflection.py`, the `JsonValue` alias (`types.py`), and `AppUtils`/`Base64` (`utils.py`).
    `fs/` — atomic writes, backups and path guards (`paths.py`), content digests (`hashing.py`),
    cross-process locks and atomic symlinks (`locks.py`), generator-owned fenced blocks
    (`blocks.py`), TOML/YAML/JSON round-trip documents (`documents.py`). `data/` — Excel/pandas
    helpers behind optional extras. `logging/` — structured logging built on `verboselogs` with a
    Rich handler that writes to **stderr**, plus a `structlog` front end. `runtime/` — env-var
    access and fail-fast guards (`environment.py`), subprocess/task helpers, failure-isolated
    entry-point plugin loading (`plugins.py`). `integration/` — messaging/secrets/objects protocols
    and the resilience helpers. `src/rn_forge/commons/__init__.py` is the curated public API —
    re-export new symbols there when adding public functionality. Public class names do not encode
    the grouping, so moving a module never moves a class name. Modules gated behind an optional
    extra are deliberately excluded from the facade; import them directly.
- **`packages/rn-forge-cli`** (import path `rn_forge.cli`) — the shared command-line layer for every
    `rn-forge-*` application, developer tool or not. Hard dependencies on `rich` and `typer`:
    a Rich output facade (`console.py`), the Typer application factory (`app.py`), the standard
    option set and CLI value parsers (`options.py`), the error-to-exit-code mapping and the `run`
    wrapper a `main()` uses (`errors.py`), and the declared `[cli]` surface of kiln ADR-0009
    (`declare.py`). `src/rn_forge/cli/__init__.py` is the curated public API; `declare` is
    deliberately imported directly, since it reads a repository's configuration document.
- **`packages/rn-forge-tooling`** (import path `rn_forge.tooling`) — the file-owning developer
    tooling: a locked JSON state store with an envelope-metadata field (`state.py`), a strict Jinja
    render engine (`templates.py`), the generation engine split into vocabulary, classification and
    transactional apply (`generation/`), release-bundle extraction (`install/`), the
    documentation-tree checkers and their injected `DocsPolicy` (`docs/`), and this package's own
    command surfaces (`cli/`, which ships `rn-forge-docs`). Depends on `rn-forge-cli`, which
    depends on `rn-forge-commons`. Hard dependencies on `jinja2` and `markdown`. The facade is
    lazy: importing `rn_forge.tooling` does not import Jinja.
- **`packages/rn-forge-web`** (import path `rn_forge.web`) — framework-agnostic HTTP/API
    primitives: the wire semantics an application promises its callers, shared by Django/DRF,
    FastAPI/Starlette and anything else that speaks HTTP. The correlation ID (`context.py`), RFC 9457
    problem details and the MRO-resolving exception registry (`problem.py`, `exceptions.py`), ETag
    `If-Match` preconditions (`concurrency.py`), AIP-158 opaque-cursor pagination (`pagination.py`),
    the idempotency-store protocols and request hashing (`idempotency.py`), readiness-check
    aggregation (`health.py`), a pure-ASGI correlation middleware with locally-declared ASGI type
    aliases (`asgi.py`), the `Principal`/authenticator/authorizer contract and the 401/403 +
    `WWW-Authenticate` rules (`auth.py`), and `conformance/` — the scenario table, shipped as
    framework-free **data**, that each framework package runs its own stack through. Nine modules,
    all one kind of mechanism (inbound HTTP wire semantics), so the package is deliberately **flat**
    (kiln D55). Depends on `rn-forge-commons` and **nothing else**: no third-party dependency at all,
    both Phase 0 candidates (`asgi-correlation-id`, `rfc9457`) having been evaluated and rejected —
    the reasons are in the package README's "Dependencies and why". `src/rn_forge/web/__init__.py` is
    the curated public API. `docs/adoption/` is a normative deliverable, not garnish: it is what an
    application's specification is written against.
- **`packages/rn-forge-django`** (import path `rn_forge.django`) — Django/DRF integration layer built on top
    of `rn-forge-commons`. Depends on `rn-forge-commons` via `[tool.uv.sources]` workspace linking (not PyPI).
    Optional extras: `drf` (djangorestframework, plus `rn-forge-commons[excel]` since `drf.views` eagerly
    imports the Excel renderer/parser), `jwt` (`drf` + djangorestframework-simplejwt), `saml` (`drf` +
    djangorestframework-simplejwt + python3-saml), `fixtures` (`rn-forge-commons[excel]`), `all` (everything
    above).

### The import boundary is executable

`.importlinter` at the repo root states the rules the dependency graph depends on, and
`uv run lint-imports` proves them (CI gates every other job on it):

1. `rn_forge.commons` never imports `rn_forge.cli`, `rn_forge.tooling`, Typer or Jinja — it is
   runtime-neutral and ships into web servers and containers.
2. `rn_forge.cli` never imports `rn_forge.tooling` or Jinja — a batch application takes the
   command-line layer without the file-owning machinery (kiln D52, ADR-0002).
3. The three libraries layer strictly: `tooling` → `cli` → `commons`.
4. `rn_forge.django`'s runtime surface never imports any of them. Only `rn_forge.django.codegen`
   may, and only with the (not yet built) `codegen` extra installed.
5. `rn_forge.web` imports no web framework (`django`, `fastapi`, `starlette`, `rest_framework`) and
   neither `rn_forge.cli` nor `rn_forge.tooling` — it ships into an ASGI server and has no business
   reaching the command-line or file-owning layers. The framework packages layer on top of it:
   `django → web → commons`, with `fastapi` an independent sibling of `django` (an optional layer in
   the contract until that package exists), so neither may import the other.

There are deliberately **no compatibility re-exports** in any direction — a shim would satisfy a
caller and reverse the dependency. When moving a symbol across the boundary, move it; do not alias
it.

### Releases are pinned git tags, not PyPI versions

None of these packages is published to PyPI. A release is a tag
(`rn-forge-commons-v0.5.0`), and every consumer — including `rn-forge-cli` and `rn-forge-tooling`
depending on `rn-forge-commons` — declares it as a pinned direct URL
(`rn-forge-commons @ git+https://github.com/rn-forge/pykit@<tag>#subdirectory=packages/<pkg>`),
per kiln D46. The `[tool.uv.sources]` workspace override exists for local development only; it is
what makes the workspace resolve to the checkout, and it is not what a consumer resolves.

All four packages use `uv_build` as the build backend with `module-name` mapped to their `rn_forge.*` namespace
package, and all ship a `py.typed` marker (strict typing is a contract of these libraries).

## Design principles

These hold for every existing package and for every future ideation — new modules, new packages, new extras. When a plan or a change conflicts with one of these, the principle wins unless the deviation is written down with its reason.

### 1. Don't reimplement a proven library

If a maintained, widely-used third-party library already does the job, **depend on it**. Do not hand-roll an equivalent for the sake of a small dependency footprint. "Zero dependencies" is not a goal of this workspace; a small, deliberate, well-chosen dependency set is.

Hand-roll only when one of these is true, and say which one in the module docstring:

- Nothing maintained covers the concern (check PyPI before concluding this, not memory).
- The candidate drags in a framework that would break a package boundary (see #3).
- The needed slice is genuinely a few lines and the candidate is unmaintained or far heavier.

### 2. Wrap third-party libraries for one design language

Depending on a library does not mean exposing its setup syntax. When a library's configuration or call syntax is verbose, stringly-typed, or inconsistent with the rest of pykit, ship a **thin wrapper** so every `rn-forge-*` package looks and behaves the same:

- Configuration is a frozen dataclass (or a settings-facade field), never a kwargs soup.
- Errors surface as `AppException` subclasses.
- Logging is injected, never assumed.
- Public symbols are re-exported from the package's curated `__init__.py`.

The wrapper standardizes; it does not extend. Do not add features the library lacks, do not fork or vendor it, and keep the underlying object reachable for consumers who need the escape hatch.

### 3. Package boundaries are non-negotiable

A framework-free package never imports a web framework (`django`, `rest_framework`, `fastapi`, `starlette`). Heavy or situational dependencies live behind optional extras. Protocols are defined in the lowest package that can hold them; adapters live in the package that owns the technology.

### 4. pykit is upstream; applications are downstream

These libraries exist so that applications built on them share logic and read alike. Surveys of existing applications are **prior art that informs the design**, not compatibility constraints to preserve — where an application got something wrong, fix it here rather than encoding it. Every package ships enough documentation (public API, wiring guides) that an application's specification can be written against pykit rather than reinventing the same primitives.

## Commands

Run all commands from the repo root unless testing a single package.

```bash
uv sync --all-extras                     # install workspace + all optional extras
uv run pytest                            # run tests across the workspace
uv run pytest packages/rn-forge-cli       # run one package's tests
uv run pytest -k test_name                # run a single test by name/keyword
uv run pytest -m unit                     # rn-forge-django only: fast isolated tests
uv run pytest -m integration              # rn-forge-django only: DB-backed tests
uv run ruff check .                       # lint
uv run ruff format .                      # format
uv run pyright                            # type check (strict mode, see below)
uv run lint-imports                       # enforce .importlinter package boundaries
```

Per-package commands work the same way with `--directory packages/<pkg>` or by `cd`-ing into the package first (each package has its own `pyproject.toml`/`dev` dependency group). Each package's `dev`/`docs` dependency groups self-reference their own `all` (django) / `excel` (commons) extra — e.g. `dev = ["rn-forge-django[all]", "assertpy>=1.1", ...]` — so a `--group dev` sync always exercises every optional code path instead of silently skipping `pytest.importorskip`-gated tests.

### Type checking scope

Root `pyproject.toml` configures Pyright in `strict` mode, `include = ["packages"]`, ignoring `tests`
and the two framework examples in `rn-forge-web/docs/adoption/examples/` (they import Django and
FastAPI, which that package deliberately does not install; the framework-free `asgi_app.py` beside
them **is** typechecked, and is executed by the test suite against the conformance table). Test code is intentionally excluded from strict typing; library source under `src/` is not — new source code must satisfy strict mode (explicit types, no untyped `Any` leakage across public APIs).

### Docs

`rn-forge-commons`, `rn-forge-cli`, `rn-forge-tooling` and `rn-forge-web` each have an mkdocs site (`packages/<pkg>/mkdocs.yml`, `docs/` dir, `mkdocstrings` autogenerating API docs from docstrings under `src`), and the root `mkdocs.yml` includes them all via the monorepo plugin. Build with `uv run --group docs mkdocs build --strict` from a package directory, or from the repo root for the combined site. Per-package builds are strict, so a cross-package link will fail the build — reference the other package by name instead of linking into it. Keep docstrings accurate since they are the doc source, not just IDE hints.

## Architecture notes

### Settings facade pattern (rn-forge-django)

`rn_forge/django/settings.py` exposes a single module-level `rn_forge_django_settings` instance (a frozen dataclass tree: `RnforgeDjangoSettings` → `AuthSettings`/`DRFSettings` → nested settings). It is built once from the Django `RN_FORGE_DJANGO` setting dict and rebuilt automatically via a `setting_changed` signal handler (`_reload_settings`), which matters for tests using `override_settings`. When adding a new configurable option: add a `TypedDict` field to the relevant `*SettingsDict`, a field on the matching frozen dataclass, and wire extraction in `_build_settings()` using `DictUtils.get`/`_get_mapping` for nested path lookups (e.g. `"DRF.VIEWS"`).

### Model base classes (rn_forge.django.models)

`models/base.py` defines the abstract model hierarchy nearly all concrete models should build on:

- `BaseModel` — adds `status` (`EnumField` over `Status` enum), `created_by`/`created_at`/`updated_by`/ `updated_at` audit columns (DB columns are camelCase for legacy compatibility, Python fields are snake_case), a `NaturalKeyLookupManager` default manager, `TruncateModelMixin`, and `FixtureModelMixin`.
- `DateModel` / `DateRangeModel` — extend `BaseModel` with date/date-range fields.
- Validation-on-save is opt-in: set `validate_on_save = True` on a model to have `save()` call `full_clean()` automatically; `get_full_clean_exclude()` controls which fields are excluded when a partial `update_fields` save is used.
- Natural-key fixture loading: implement `natural_keys()` (list of field names, dotted paths allowed) on a model to get `get_by_natural_key()`/`natural_key()` support for Django fixtures.

### Auth package (rn_forge.django.auth)

Sub-namespaced by auth mechanism: `auth/basic`, `auth/jwt`, `auth/saml`, plus shared `auth/drf` (DRF authentication classes, permissions, mixins, serializers) and `auth/credentials.py`/`auth/payload.py` for the common credential/payload shapes. The app is registered under the stable label `rn_forge_django_auth` (`auth/apps.py`) so fixtures/migrations/admin registration have a fixed reference point independent of the Python import path.

### DRF integration (rn_forge.django.drf)

`drf/views/` provides base view classes and mixins (`base.py`, `mixins.py`, `bulk.py`) plus transfer/export helpers (`excel.py`, `transfer.py`, `parsers.py`, `renderers.py`) — these read `DRFViewsSettings` from the settings facade above (transfer format, row limits, permission-action map). `drf/serializers/` provides a `base.py` serializer and custom `fields.py`. `drf/exceptions.py` maps this package's exceptions to DRF error responses.

## Testing conventions

- Tests live in each package's `tests/`, mirroring the `src/rn_forge/<pkg>/` layout (e.g. `tests/fs/test_paths.py` tests `src/rn_forge/commons/fs/paths.py`, and `tests/auth/drf/test_authentication_and_permissions.py` tests `src/rn_forge/django/auth/drf/`). When a module moves, its test module moves with it.
- A test module that has to be imported *by name* (a `--policy` reference, say) needs an unambiguous alias rather than `tests.<...>` — see `rn-forge-tooling/tests/docs/test_docs.py`.
- Only `rn-forge-django` ships a `tests/__init__.py`. Do **not** add one to another package: a root-level `uv run pytest` reads no per-package `[tool.pytest.ini_options]`, so it collects without `--import-mode=importlib`, and a second directory importable as `tests` collides with django's and fails collection for the whole workspace.
- `rn-forge-web` marks its async tests with an explicit `@pytest.mark.asyncio` rather than relying on its own `asyncio_mode = "auto"`, for the same reason: that setting is not in effect when the suite runs from the repo root.
- `rn-forge-django/tests/conftest.py` configures Django (`settings.configure(...)`, sqlite in-memory DB, `django.setup()`) — no separate Django settings module exists; this conftest is the only settings source for tests.
- `rn-forge-django` defines `unit` and `integration` pytest markers (`pyproject.toml`) — mark DB-backed tests `integration` and fast isolated tests `unit`. `rn-forge-web` defines `unit`. Both emit `PytestUnknownMarkWarning` when the suite is run from the repo root, since the root has no pytest config to register them in; the warnings are cosmetic.
- `pytest-randomly` randomizes test order by default in every package — do not rely on cross-test ordering.
- Tests are excluded from ruff's lint rules (`per-file-ignores` = `ALL` for `**/tests/*`) and from Pyright's strict checking.
