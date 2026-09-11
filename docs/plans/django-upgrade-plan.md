# `rn-forge-django` upgrade plan

Scope: `packages/rn-forge-django` only. `rn-forge-commons` is out of scope here — but note the
dependency direction: this package consumes commons via workspace linking, so two phases below
(Phase 6, Phase 8) *depend on* commons phases landing first. Those dependencies are called out
explicitly where they apply; nothing here modifies commons source.

Two sources feed this plan, and it is self-contained — it does not depend on any other document:

- The Django/DRF-shaped subset of the `cims-backend` extraction survey
  (`/Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend`), performed 2026-07-22 across
  `apps/common`, `apps/core`, `apps/messaging`, `config/`. That survey's commons-shaped half
  (environment guards, resilience, CloudEvents, claim-check) was already routed into
  [`commons-upgrade-plan.md`](./commons-upgrade-plan.md) and is **not** repeated here.
- A verification pass over `packages/rn-forge-django/src` and `tests/` performed 2026-08-31, which
  resolved the open questions the survey left ("check the existing file first", "confirm before
  assuming"). Those answers are baked into the destinations below — they are facts about this repo
  as of that date, not guesses.

## Alignment with the standardization plan (kiln revision 9)

**Written 2026-09-10.** This plan predates `rn-forge/kiln`. Every phase, every extraction decision
and the "do not improve these" list are unchanged. What changed is the workspace around it: the
library graph gained a layer, releases became tags, the package layout got a rule, and this package
acquired a named place in the archetype catalogue and in the code-generation design. Authority:
`../../../kiln/docs/plans/standardization-plan.md` (revision 9) and `../../../kiln/docs/adr/` —
chiefly ADR-0002, ADR-0005, ADR-0009, D37, D46, D53, D55 and D56.

### 1. The graph has three library layers, and none of them is above this package

The development layer split into `rn-forge-cli` and `rn-forge-tooling` (kiln **D52**), so
Convention "Django stays in this package" now has a mirror rule: **`rn_forge.django`'s runtime
surface imports neither `rn_forge.cli` nor `rn_forge.tooling`, and neither Typer nor Jinja.** That is
not a new intention — it is already an executable contract in `.importlinter`
(`django-runtime-has-no-tooling`), and `uv run lint-imports` gates every other CI job.

The one exception is `rn_forge.django.codegen`, which is §4 below.

```text
commons ──► cli ──► tooling ──► kiln / agentkit
   └──────────────────────────► web ──► django            (this package)
                                 └───► fastapi
```

### 2. `rn-forge-web` as a dependency, and the contract that has to move with it

"Dependency changes" below adds `rn-forge-web` as a base dependency. Two things must land in the same
change, or the arrow is only a claim:

1. `.importlinter` gains `rn_forge.web` in `root_packages` and the two contracts written up in the
   web plan's alignment section §2 — the framework-free contract on `rn_forge.web`, and a layers
   contract placing `rn_forge.django` and `rn_forge.fastapi` as independent siblings above it. The
   sibling part matters here: **`rn_forge.django` must never import `rn_forge.fastapi`,** and the
   layers contract is what says so.
2. The existing `django-runtime-has-no-tooling` contract is unchanged and still applies — adding a
   dependency on web does not open a path to cli or tooling, because web cannot reach them either.

### 3. Releases are pinned git tags, not PyPI versions (D46)

"Version bump: … bump `rn-forge-django` to `0.3.0`" means **cutting the tag
`rn-forge-django-v0.3.0`**. None of these packages is on PyPI. Consequently the dependency block in
"Dependency changes" is wrong as written — a `[tool.uv.sources]` workspace override does not survive
into a built wheel, so a consumer outside the workspace could not resolve commons or web at all.
Corrected:

```toml
[project]
dependencies = [
  "django>=6.0.7",
  # kiln D46 — pinned direct URLs; `[tool.uv.sources]` below is local development only.
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
  "rn-forge-web @ git+https://github.com/rn-forge/pykit@rn-forge-web-v0.1.0#subdirectory=packages/rn-forge-web",
]

[tool.uv.sources]                   # local development only
rn-forge-commons = { workspace = true }
rn-forge-web = { workspace = true }
```

Two consequences for sequencing: **`rn-forge-web` must have a release tag before this package can
declare it**, which is a harder edge than the phase-level "⇢ web Phase N" blocks already listed; and
the package's installation guide documents the `git+…@tag` form, including for each extra
(`rn-forge-django[drf] @ git+…`), never `uv add rn-forge-django`. The equivalent omission in tooling's
guide was a review finding (commons plan D.7) — do not repeat it here.

### 4. Code generation has a fixed home now (D37, D56)

This plan carries no generator, and that has not changed. What has changed is that the *destination*
is settled, so nothing here should drift toward it by accident:

- Django generators — model, serializer, viewset, admin scaffolds — ship as
  **`rn-forge-django[codegen]`**, live in `rn_forge.django.codegen` and nowhere else, and register
  under the entry-point group `rn_forge.kiln.generators`. kiln supplies only the Typer command
  surface (`kiln generate django app billing`).
- kiln generates **repo shape**; a framework generates its own code (**D56**). `kiln generate package`
  is kiln's; a Django model scaffold is this package's.
- The fence exists before the first codegen module: `.importlinter`'s
  `django-runtime-has-no-tooling` contract already carries the `rn_forge.django.codegen -> *`
  exemptions, and `import rn_forge.django` must succeed with no extras installed.

If a phase in this plan ever starts rendering a template, it is in the wrong subpackage.

### 5. Layout (D55)

Commons, cli and tooling were re-laid-out into sub-packages by kind of mechanism.
`rn-forge-django` **already has that shape** — `models/`, `auth/{basic,jwt,saml,drf}/`,
`drf/{views,serializers}/` — so D55 requires no move here. What it does impose: public class names do
not move when a module does, and there are no compatibility re-exports in any direction. Convention 4
("re-export from the sub-package `__init__`, not the top-level one") is unaffected and still correct
for this package.

New modules land in the sub-package that matches their mechanism: Phase 7's middleware and Phase 8's
`models/sequences.py` already do; Phase 10's `messaging/` is its own sub-package and Django app,
which is the right shape.

### 6. The consumer is an archetype, and a claim needs a golden repo

The cims successor is a kiln **`python-web-app`** repo with `framework = django` and
`frontend = angular` (**D53**), rebuilt rather than migrated (**D39**) — which is the formal version
of this plan's existing "cims is prior art, not a compatibility constraint" stance.

Under kiln **ADR-0005**, a claim not demonstrated in a runnable golden repo is not demonstrated. So
`golden/python-web-app-django` (kiln Phase E) is where this package's wiring is proved end to end:
`uv sync && task validate` in that repo, with the settings facade, the problem-details handler, the
pagination class and the correlation middleware actually wired. Phase 12's docs-only recipes and the
web plan's `wiring-django.md` are the prose form of the same thing, and the golden repo is authored
from them.

That also fixes the shape of the `[cli]` question for a Django repo: management commands stay Django's
`manage.py`; the declared `[cli]` surface of ADR-0009 belongs to `python-app`/`python-tool` repos, not
to this package. Do not add a Typer surface to `rn-forge-django`.

### 7. Repo shape and validation

`rn-forge-django` is an existing member of pykit (`python-lib` archetype), so nothing has to be added
to the workspace for it. Two ongoing obligations once kiln Phase F.1 regenerates pykit's skeleton:
the package stays listed in `[archetype.python-lib] packages` (it drives the generated per-package CI
matrix and the release job), and `.rn-forge/kiln/state.json` is re-seeded by `kiln apply` whenever a
generated file changes — `task lint` fails with `has drifted from the committed state` until it does.

Every phase's validation block gains `uv run lint-imports`. After Phase F.1, `task validate` is what
CI runs and the `uv run …` forms below are its inner primitives.

### 8. What did not change

Every phase's content, the gates on Phases 10 and 11, the extras design (including `oidc` being its
own extra and there being no `messaging` extra), the conventions, and the additive-only promise.

## Summary (read this first)

Everything here is **additive**. No existing public API in `rn-forge-django` is removed or changed
in shape; the one settings-facade change (Phase 2) adds a new nested dataclass following the exact
pattern already used by `DRFViewsSettings`.

**Part A — no new third-party dependencies** (but see the new `rn-forge-web` workspace dependency
below). Small, self-contained, one PR per phase.

Phases marked **⇢ web** are adapters over `rn-forge-web` and cannot start until the named phase of
[`web-library-plan.md`](./web-library-plan.md) has landed — see [`README.md`](./README.md) for the
full cross-plan order.

| Phase | What | Blocked on | Breaking? | Risk |
| --- | --- | --- | --- | --- |
| 0 | Test-harness prerequisites (cache backend, shared table-creation fixture) | — | no | none |
| 1 | DRF `problem_details_exception_handler` adapter | **⇢ web Phase 2** | no | low |
| 2 | **`CursorPagination`** (AIP-158) + legacy page-number + `PaginationSettings` | **⇢ web Phase 4** | no | low |
| 3 | `CacheIdempotencyStore` adapter (Django cache) | **⇢ web Phase 5** | no | low |
| 4 | `VersionedModelMixin`, `ImmutableModelMixin`, `enforce_version` | **⇢ web Phase 3** (4.3 only) | no | low |
| 5 | `OmitEmptyMixin` serializer mixin, `PermissionByMethodMixin` view mixin | — | no | none |
| 6 | Readiness-view factory + Django-flavoured settings guard | **⇢ web Phase 6**, commons Phase 7 | no | low |

**Part B — new modules, one new optional extra.**

| Phase | What | New deps | Breaking? | Risk |
| --- | --- | --- | --- | --- |
| 7 | `middleware.py` — WSGI correlation-ID middleware | **⇢ web Phase 1** | no | low |
| 8 | `models/sequences.py` — sequence-backed human-readable code generator | — | no | **medium** |
| 9 | `auth/jwt/oidc.py` — JWKS bearer **binding** over the web `Principal` contract, + basic auth | `oidc` extra (`pyjwt[crypto]`) | no | medium |

**Part C — gated subsystems. Do not start these without passing the gate.**

| Phase | What | New deps | Breaking? | Risk |
| --- | --- | --- | --- | --- |
| 10 | **Gated:** `messaging/` — outbox/inbox models, relay, consumer (bus + registry come from commons Phase 8b) | none | no | **high** |
| 11 | **Gated:** `celery.py` — app factory + retryable-task preset | `celery` extra | no | medium |
| 12 | **Code:** camelCase wiring, DRF schema mirrors, `SPECTACULAR_SETTINGS` | `openapi` extra (`drf-spectacular`, `djangorestframework-camel-case`) | no | low |
| 13 | Conformance driver over `rn_forge.web.conformance.CASES` | **⇢ web Phase 11** | no | low |
| — | Deferred: claim-check pattern, Azure adapters, `RawPassthroughField` | — | — | — |

Phases 0-6 are safe and should be done in order (Phase 0 first — the later ones need its fixtures).
Phases 7-9 are independent of each other and of Part A, other than following the conventions below.
**Phases 10 and 11 each have an explicit abort gate** — read the gate section before writing any
code for them.

### Guiding principle for this plan

Everything extracted from cims arrives with cims-shaped assumptions baked in: a hardcoded OTel
counter, a Walgreens Entra claim shape, a `/cims/backend` event source, a 24-hour cache TTL, a
`PO-2026-0001` code format. **The extraction is not done until each of those is a parameter.** The
rule for every phase:

- **Parameterize what was hardcoded; do not generalize what was not.** A hardcoded constant becomes
  a keyword argument with the cims value as its default. A single concrete implementation does *not*
  become a `Protocol` with one implementer — that is how you get the wrong abstraction (see the
  deferred claim-check item).
- **Factories over module-level singletons.** cims's relay is a `@shared_task`, its handler registry
  is a module-level dict, its readiness view is a module-level function reading module-level config.
  Each becomes a factory that takes its collaborators as arguments, so multiple instances can
  coexist in one process and tests need no monkeypatching.
- **Opt-in, never a default swap.** Nothing here changes what an existing consumer gets by doing
  nothing. The RFC 7807 handler sits alongside `drf_exception_handler`; the concurrency behaviour is
  a mixin, not a change to `BaseModel`.
- **Django stays in this package.** No Django import may be added to `rn-forge-commons` by any phase
  here. Where a phase needs a commons capability, it wraps the Django-free commons API.

### Conventions for new modules

The first three are standing design decisions carried over from the cims survey; the rest are
existing repo conventions, restated so this document is self-contained. They are the same
conventions the commons plan states, adjusted for this package's layout.

1. **Logging is injected in any module whose logging is observable behaviour.** cims uses
   `structlog`; this package logs through `AppLogger.get_logger(__name__)`. Any new module that logs
   as part of what a consumer *observes* — the request-ID middleware's `request.complete` line, the
   outbox relay's per-batch line — takes a logging callable as a constructor/factory parameter,
   defaulting to a thin `AppLogger` wrapper. Ordinary internal debug logging stays on `AppLogger`
   directly. (The commons plan's Phase 9 explores a structlog front-end; do not pre-empt or depend
   on its outcome here — the injected-callable shape is correct either way.)
2. **Metrics are optional hooks, never a hard dependency.** cims increments OpenTelemetry counters
   inline (`circuitbreaker_state`, `outbox_lag`). New modules accept plain callables
   (`on_state_change`, `on_lag_observed`) that a consumer wires to their own metrics backend.
   `opentelemetry-api` must not become a dependency of this package.
3. **`BaseModel` is not being replaced.** cims's `apps/common/models.py::BaseModel` (UUID PK,
   `version` int, plain audit columns) and this package's
   `rn_forge.django.models.base.BaseModel` (`status` `EnumField`, camelCase `db_column`s,
   `NaturalKeyLookupManager`, `validate_on_save`) are different, both-reasonable designs.
   Phase 4 extracts cims's version/immutability *behaviour* as standalone mixins that compose with
   either base. **Do not** add `version` to `BaseModel`, and do not add a `status` field or
   camelCase `db_column`s to anything new.
4. **Re-export from the sub-package `__init__`, not the top-level one.** Verified 2026-08-31:
   `src/rn_forge/django/__init__.py` is an empty-`__all__` docstring module — it is *not* a curated
   public API like `rn_forge/commons/__init__.py`. The curated surfaces are the sub-package inits:
   `models/__init__.py`, `drf/__init__.py`, `drf/serializers/__init__.py`, `drf/views/__init__.py`,
   `auth/**/__init__.py`. New public symbols go into the matching one, with `__all__` kept sorted.
   Do not start populating the top-level `__init__.py` as part of this plan.
5. **New extras aggregate into `all`.** When adding an optional extra, add its packages to the `all`
   extra too, and gate the corresponding tests with `pytest.importorskip` following the pattern
   already used in `tests/test_views.py:7`.
6. **Follow the repo's module conventions.** Module docstring at the top of the file; explicit
   `__all__`; `from __future__ import annotations`; `AppException` /
   `AppException.check(value, "msg {}", arg)` for validation rather than a raw `raise`; `{}`-style
   log message formatting.
7. **Strict typing is a contract.** `src/` must satisfy Pyright strict mode (root `pyproject.toml`,
   `include = ["packages"]`); `tests/` is excluded, as it is from ruff lint. Django's stubs are
   incomplete in places — follow the existing precedent of a narrowly-scoped
   `# pyright: ignore[reportUnknownMemberType]` with a trailing comment saying why (see
   `settings.py:206`), never a file-level suppression.
8. **Mark every test.** `unit` for isolated tests, `integration` for DB-backed ones — both markers
   are declared in `packages/rn-forge-django/pyproject.toml`. `pytest-randomly` randomizes order;
   no test may depend on another's side effects.

### Things deliberately NOT extracted (decided; do not "improve" these)

- **Anything under cims `apps/core`, `apps/audit`, `apps/bff`, `apps/ariba`, `apps/hana`,
  `apps/nexia`.** Inventory/SAP/Nexia business logic. The Protocol/Stub/Http client triplets in the
  integration apps stay in cims — only the `ResilientHttpClient` base they wrap is generic, and that
  one is commons' Phase 8, not this plan's.
- **The Azure Service Bus and Azure Blob Storage adapters.** cims becomes the Azure adapter for this
  package's generic protocols, not the other way round. Same for the `run_consumer` /
  `resubmit_dlq` management commands.
- **`AuditContextMiddleware`'s header-trust mechanism** (`X-CIMS-Actor` / `X-CIMS-Role`). That is a
  dev-convenience auth bypass. Do not normalize it into a library. Only the request-ID half of
  cims's middleware module is extracted (Phase 7).
- **`drf/views/transfer.py`.** Its ~1,200 lines substantially overlap `django-import-export` +
  `tablib`, which is worth revisiting — but it is not a cims extraction and it is not in this plan.
- **The `RequestUtils` name collision** between `django/utils.py:40` and `django/drf/utils.py:49`
  (different APIs, no shared logic). Known, recorded, out of scope — renaming either is a breaking
  change that needs its own plan.

### Python floor: no change, and no longer a prerequisite

`rn-forge-django` stays at `requires-python = ">=3.14"`. An earlier version of this note made cims's
3.12 pin (ADR-001) a prerequisite for cims consumption. That is void: cims is work-in-progress and
being rewritten from a new specification against these libraries, so its current pin constrains
nothing here. See the web plan's Phase 0.1.

The commons plan's Phase 0 still replaces `commons/logging.py`'s parenthesis-free `except` with the
parenthesized form — it costs nothing and removes a gratuitous version gate — but nothing depends on
it any more.

### Dependency changes (apply incrementally, one phase at a time)

**New base dependency: `rn-forge-web`.** Phases 1, 3, 4.3, 6.1 and 7 are all adapters over it, so it
is a hard dependency of the package rather than an extra:

```toml
[project]
dependencies = ["django>=6.0.7", "rn-forge-commons", "rn-forge-web"]

[tool.uv.sources]
rn-forge-commons = { workspace = true }
rn-forge-web = { workspace = true }
```

> **Corrected by the alignment section, §3.** Both rn-forge entries are pinned direct URLs at release
> tags (kiln D46); the `[tool.uv.sources]` block is local development only and does not survive into
> a built wheel. Use the form given there, not the one above.

The dependency direction across the workspace is `django → web → commons`, with
`azure → commons` alongside it. Nothing in `rn-forge-web` may import Django (its own boundary check
enforces that), so this arrow only ever points one way.

`packages/rn-forge-django/pyproject.toml`:

```toml
[project.optional-dependencies]
drf = ["djangorestframework>=3.17.1", "rn-forge-commons[excel]"]
fixtures = ["rn-forge-commons[excel]"]
jwt = ["djangorestframework>=3.17.1", "djangorestframework-simplejwt>=5.5.1"]
oidc = ["djangorestframework>=3.17.1", "pyjwt[crypto]>=2.10.1"]   # phase 9
# celery = ["celery>=5.5.3"]                                      # phase 11 ONLY IF the gate passes
saml = [...]                                                      # unchanged
all = [
  "djangorestframework>=3.17.1",
  "djangorestframework-simplejwt>=5.5.1",
  "pyjwt[crypto]>=2.10.1",   # phase 9
  "python3-saml>=1.16.0",
  "rn-forge-commons[excel]",
]
```

Two deliberate deviations from the original survey's dependency shape:

- **`oidc` is its own extra, not folded into `jwt`.** `pyjwt` is available transitively today via
  `djangorestframework-simplejwt`, but JWKS bearer auth (externally-issued tokens, no local `User`)
  has nothing to do with simplejwt-issued tokens. A consumer wanting Entra/Auth0/Okta auth should
  not be made to install simplejwt to get it. Declaring `pyjwt[crypto]` directly also removes a
  silent transitive-version dependency.
- **No `messaging` extra.** The survey proposed one, but Phase 10 needs no third-party package — it
  is Django ORM plus stdlib, and no library was found that does transactional outbox/inbox over the
  Django ORM (record that negative result in the module docstring per the workspace principle) — and
  an empty extra is a maintenance artifact that installs nothing.
  Isolation comes from it being a separate sub-package the consumer must add to `INSTALLED_APPS`,
  which is a stronger guarantee than an extra anyway. If Phase 10 ever grows a real dependency,
  create the extra then.

**Version bump:** everything here is additive, so bump `rn-forge-django` to **`0.3.0`** once Part A
lands, and again only if Part C ships.

### Validation command for every phase

Run from the repo root after each phase. Do not proceed to the next phase with any of these red:

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-django
uv run ruff check packages/rn-forge-django
uv run ruff format --check packages/rn-forge-django
uv run pyright                       # strict mode; src/ must be clean, tests are excluded
uv run lint-imports                  # the boundary contracts — alignment §§1-2, 4
uv run --directory packages/rn-forge-django --group docs mkdocs build --strict
```

`mkdocs build --strict` fails on a nav entry pointing at a missing file, so add the page and the
`mkdocs.yml` nav entry in the same commit as the module.

---

## Part A — No new dependencies

### Phase 0 — Test-harness prerequisites

No source changes. Do this first: Phases 3, 4, 8 and 10 all need infrastructure the test suite does
not have today, and discovering that mid-phase turns a small change into a debugging session.

**What is missing.** Verified against `tests/conftest.py` (26 lines) on 2026-08-31:

1. **No `CACHES` configuration.** `settings.configure(...)` sets `DATABASES`, `INSTALLED_APPS`,
   `ALLOWED_HOSTS`, `DEFAULT_AUTO_FIELD`, `USE_TZ` and nothing else. Django's implicit default is
   locmem, which works — but Phase 3's idempotency tests need a *guaranteed* backend and need it
   cleared between tests, and relying on an implicit default that Django could change is not worth
   the saved line.
2. **No shared table-creation fixture.** `tests/test_models.py:300-305` defines a module-scoped
   `_django_tables` autouse fixture that runs `connection.schema_editor()` over the test-only models
   declared at the top of that file, under `django_db_blocker.unblock()`. Phases 4, 8 and 10 each
   need the same thing for their own test-only models, and copying that fixture four times is how it
   drifts.

**Steps.**

1. Add `CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}` to
   `settings.configure(...)` in `tests/conftest.py`, plus a function-scoped autouse fixture that
   calls `cache.clear()` — `pytest-randomly` means a cached response from one test can otherwise
   land in another.
2. Extract the table-creation fixture into `tests/conftest.py` as a reusable factory, e.g.
   `create_tables(*models)` used from each test module's own module-scoped autouse fixture. Keep the
   `django_db_setup` / `django_db_blocker.unblock()` shape exactly as `test_models.py` has it —
   that part is correct, it is only the location that is wrong. Repoint `test_models.py` at it and
   confirm that file still passes on its own (`uv run pytest packages/rn-forge-django/tests/test_models.py`).
3. Document the test-only-model convention in `tests/conftest.py`'s docstring: concrete models
   declared in the test module, `class Meta(<Base>.Meta): app_label = "rn_forge_django"`, tables
   created by the fixture. This is what `test_models.py` already does; writing it down stops the
   next phase from inventing a second convention.

**Known limitation to record now, not discover later.** The test database is sqlite in-memory.
sqlite does not support `select_for_update()` at all, and Django raises `NotSupportedError` for
`skip_locked`. Phases 8 and 10 both depend on row-level locking for their *production* path. Neither
can be fully covered by the default test suite; each phase below says explicitly what its sqlite
coverage does and does not prove. Do not "fix" this by weakening the production query.

**Phase 0 exit criteria:** validation suite green; `tests/test_models.py` passes in isolation and in
a full run; `grep -n "schema_editor" packages/rn-forge-django/tests/` shows exactly one occurrence
(in `conftest.py`).

---

### Phase 1 — DRF adapter over `rn_forge.web.problem`

> **Rewritten by [`web-library-plan.md`](./web-library-plan.md) §A.1.** This phase originally
> specified the exception classes *and* an RFC 7807 body builder inside `rn_forge.django`. Both now
> live in `rn-forge-web`, because a FastAPI service needs exactly the same thing and cannot import
> Django to get it. **Prerequisite: web plan Phases 0 and 2 have landed.** What remains here is a DRF
> `exception_handler` adapter — roughly 30 lines, not a module.

**Source:** cims `apps/common/exceptions.py` (`problem_details_handler`, `DomainConflict`,
`VersionConflict`) — prior art only; the shipping design is the web plan's Phase 2.

#### 1.1 — The exception classes are **not** defined here

`DomainConflict`, `VersionConflict`, `PreconditionRequired`, `MalformedPrecondition`, `InvalidCursor`,
`IdempotencyKeyRequired` and `IdempotencyKeyReuse` are defined in `rn_forge.web.exceptions`, all
subclassing `rn_forge.commons.exceptions.AppException`.

An earlier version of this phase put `DomainConflict`/`VersionConflict` in
`rn_forge/django/exceptions.py`, arguing that their only consumers were Django-shaped and commons had
no caller. **That reasoning is superseded, not wrong:** `rn-forge-web` is the caller that was missing.

- `rn_forge/django/exceptions.py` gains **no new classes**. If a convenience re-export is wanted,
  re-export from `rn_forge.web.exceptions` rather than subclassing — a parallel Django-side hierarchy
  would mean `except DomainConflict` catching only half the raises.
- `rn-forge-django` gains a dependency on `rn-forge-web` (see the dependency section).

#### 1.2 — `problem_details_exception_handler`

**Destination:** `src/rn_forge/django/drf/exceptions.py`, alongside the existing
`drf_exception_handler` (that file is 34 lines today — no new module needed).

```python
def problem_details_exception_handler(
    exc: Exception,
    context: Mapping[str, object],
    *,
    registry: ProblemRegistry | None = None,
) -> JsonResponse:
    """Render an exception as an RFC 9457 ``application/problem+json`` response."""
```

The adapter's whole job is translation in both directions; every policy decision belongs to the
registry, not to this function.

1. Delegate to DRF's default `exception_handler(exc, context)` **first**, so every DRF exception
   keeps its own status code and detail. Only when it returns `None` (an unhandled exception) fall
   back to the registry's fallback problem type.
2. Resolve the problem type via `registry.problem_for(exc)` — the MRO walk means no per-class
   `isinstance` ladder here, and it is where `VersionConflict` → **412** now comes from (§A.1 of the
   web plan; the old "map `DomainConflict`/`VersionConflict` → 409" instruction is **superseded**).
   `registry` defaults to `rn_forge.web.problem.default_registry()`, built once at module import; a
   consumer wanting its own type-URI base or extra rows passes one.
3. Normalize DRF's field-error shape with **`rn_forge.web.problem.errors_from_field_map`** — do not
   write a second normalizer here, and note that the web version recurses into nested serializers,
   which cims's did not. The scalar `{"detail": "..."}` shape becomes the problem's `detail` member.
   Attach the normalized list as the `errors` extension only when non-empty.
4. Build the body with `registry.build(exc, instance=..., extensions=...)` and `.as_body()`. This
   phase must not construct the `{"type", "title", "status", ...}` dict by hand — that flattening
   rule lives in one place (web §2.1) precisely so the two frameworks cannot drift.
5. Set `Content-Type: application/problem+json` —
   `JsonResponse(body, status=problem.status, content_type=PROBLEM_MEDIA_TYPE)`, importing the
   constant rather than retyping the string.
6. Stamp `instance` from the request path, and attach the correlation ID as an extension via
   `rn_forge.web.context.get_correlation_id()`. That import is unconditional now — `context.py` is a
   base-install module of a package this one depends on, so the old "import it lazily *if* Phase 7 has
   landed" dance is gone.

**Design notes.**

- Follow the existing handler's shape for getting at the request:
  `RequestUtils.get_django_request(cast(Request, context["request"]))`, imported from
  `rn_forge.django.drf.utils` — `drf/exceptions.py:11` already does exactly this.
- Log through the module's `AppLogger`, matching `json_exception_response`'s
  `_LOGGER.exception(...)` behaviour in `django/exceptions.py:31`. (Convention 1's inject-the-logger
  rule binds `rn_forge.web`, not this package.)
- **Do not re-derive status codes.** If a mapping looks wrong, fix the row in the web package's
  default registry so both frameworks change together.

**Non-goals.** Do not wire this as anyone's default `EXCEPTION_HANDLER`, do not add a setting for
choosing between the two handlers, and do not change `drf_exception_handler`. Consumers opt in
through their own `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.

**Tests.** New `tests/drf/test_problem_details_exception_handler.py` (`unit`): `DomainConflict` → 409
and `VersionConflict` → **412** (the regression guard on the amended mapping); scalar-detail
normalization; nested field-error normalization; absent `errors` key on scalar errors; content type;
`instance` and the correlation-ID extension present and absent; a custom `registry` overriding a row;
unhandled-exception 500 path with no internal detail leaked. `tests/drf/test_exceptions.py` must keep
passing unchanged — that is the regression guard on "additional, not replacement".

**Docs.** Extend `docs/api/drf/exceptions.md` with the new symbol and a short "which handler do I
want" paragraph, and link the web package's `api-conventions.md` (web Phase 9) as the normative wire
contract rather than restating it.

---

### Phase 2 — Cursor pagination (standard) and `PaginationSettings`

**Amended by the web plan (§A.1).** The original phase shipped only
`StandardPagination(PageNumberPagination)` from cims. That is now the *legacy* option: it makes a
Django API structurally un-swappable with a FastAPI one, because the two would disagree on the
envelope, the query parameters and the continuation mechanism on every list endpoint. Page-number
pagination is not wrong — it is a different contract, and the shared kit has to pick one.

**Source:** cims `apps/common/pagination.py::StandardPagination` (legacy half);
`rn_forge.web.pagination` + web plan §4.1 (standard half).
**Destination:** new `src/rn_forge/django/drf/pagination.py`.

#### 2.0 — `CursorPagination` is the standard class

```python
class CursorPagination(drf_pagination.CursorPagination):
    """Keyset pagination emitting the AIP-158 envelope over the shared cursor codec."""


class LegacyPageNumberPagination(PageNumberPagination):
    """Page-number pagination. Use only where a total and a jumpable index are required."""
```

**Subclass DRF's own `CursorPagination`; do not reimplement keyset paging.** Its ordering handling,
its `WHERE (sort_key, pk) > (...)` construction and its edge cases are proven, and principle #1 says
depend on that. Override exactly three things:

1. **the cursor codec** — `encode_cursor`/`decode_cursor` delegate to `rn_forge.web.pagination`, so a
   token issued by the Django stack is structurally the same token the FastAPI stack issues;
2. **the query parameters** — `pageToken` and `pageSize`, not DRF's `cursor` and `page_size`;
3. **`get_paginated_response` and `get_paginated_response_schema`** — emit the AIP-158 envelope
   (`items`, `nextPageToken`, optional `totalSize`), and the schema override is what keeps
   drf-spectacular's output agreeing with FastAPI's.

Clamp `pageSize` to the cap; **never reject an over-large value** with a 400 — web §4.1, and AIP-158's
own rule. DRF will not do this for you.

**The `reverse` decision is made here** (web plan §4.3). DRF's cursor carries a `reverse` flag so it
can serve a previous page; `rn_forge.web.pagination.Cursor` has no such field and AIP-158 is
forward-only. Either add `reverse: bool = False` to the web `Cursor` — three lines there, and FastAPI
never sets it — or disable reverse paging here. **Decide, record it in both plans, and do not let the
two packages answer differently**: a `previousPageToken` on one stack and not the other is exactly the
divergence the shared package exists to prevent.

`LegacyPageNumberPagination` keeps cims's class defaults `page_size=50`,
`page_size_query_param="pageSize"`, `max_page_size=200`, all three overridable through the settings
facade. **The name carries the status** — a class called `StandardPagination` will keep being chosen
by default no matter what a guide says. There is no compatibility alias, per the workspace rule.

#### 2.1 — Settings-facade wiring

Add a `PaginationSettings` layer nested under `DRFSettings`, following `DRFViewsSettings` exactly
(`settings.py` is 206 lines and the pattern is unambiguous — copy it, do not improvise):

1. `class PaginationSettingsDict(TypedDict, total=False)` with `PAGE_SIZE: int`,
   `PAGE_SIZE_QUERY_PARAM: str`, `MAX_PAGE_SIZE: int`.
2. `PAGINATION: PaginationSettingsDict` on `DRFSettingsDict`.
3. `@dataclass(frozen=True) class PaginationSettings` with `page_size`,
   `page_size_query_param`, `max_page_size` and module-level `_DEFAULT_*` constants beside the
   existing `_DEFAULT_TRANSFER_FORMAT` / `_DEFAULT_EXPORT_MAX_ROWS` block.
4. `pagination: PaginationSettings = field(default_factory=PaginationSettings)` on `DRFSettings`.
5. Extraction in `_build_settings()` via `_get_mapping(config, "DRF.PAGINATION")`, same `cast` +
   `.get(KEY, _DEFAULT)` idiom as the views block.
6. All five new names added to `settings.py`'s `__all__`, sorted.

**The reload trap.** `rn_forge_django_settings` is rebound by `_reload_settings` on the
`setting_changed` signal (`settings.py:193-205`). A class attribute evaluated at import time would
freeze the value from first import and silently ignore `override_settings`. So
**both** pagination classes **must** read the facade at request time — override the
`get_page_size(request)` method and read `rn_forge_django_settings.drf.pagination` inside it, and
import the *module* (`from rn_forge.django import settings as rnf_settings`) or the module-level
name in a way that re-reads the rebound global. Assert this with a test that uses
`override_settings` and checks the *new* value takes effect. This applies to `CursorPagination` too,
and it is easier to get wrong there because DRF's own class reads `page_size` as a class attribute.

**Tests.** New `tests/drf/test_pagination.py` (`unit`): class defaults for both classes; each of the
three settings overridden through `override_settings(RN_FORGE_DJANGO={...})`;
reload-after-`setting_changed` on both. For `CursorPagination` specifically: the AIP-158 envelope
(`items`/`nextPageToken`, `totalSize` absent by default); a token round-trips through
`rn_forge.web.pagination` and **decodes with the shared codec, not DRF's** — assert that directly,
since a silent fallback to DRF's encoding is the failure that breaks cross-stack token parity;
`pageSize` above `max_page_size` is **clamped to the cap and returns 200**, never a 400; a tampered
`pageToken` raises `InvalidCursor` and renders as a 400 problem body. For
`LegacyPageNumberPagination`: the `pageSize` query-param honoured and clamped.

**There is no existing settings test to copy.** Verified 2026-08-31: no test in
`packages/rn-forge-django/tests/` uses `override_settings` or touches `rn_forge_django_settings` at
all, so the `_reload_settings` signal handler (`settings.py:193`) is currently uncovered. This phase
is the right moment to add `tests/test_settings.py` covering the facade generally — defaults,
override, reload — not just the pagination block. That is a small extra scope worth taking here
because Phase 2 is the first thing that would break if the reload path regressed.

**Docs.** New `docs/api/drf/pagination.md` + nav entry under `API Reference > DRF`; add the
`DRF.PAGINATION` block to `docs/guides/settings.md`.

---

### Phase 3 — Django-cache `IdempotencyStore` adapter

> **Rewritten by [`web-library-plan.md`](./web-library-plan.md) §A.1.** The protocol, the request
> hashing and the reuse semantics live in `rn_forge.web.idempotency`. This phase ships the Django
> adapter — and gains body-hash reuse detection the original `replay`/`remember` pair could not do.
> **Prerequisite: web plan Phase 5 has landed.**

**Source:** cims `apps/common/idempotency.py` (`replay`, `remember`) — prior art.
**Destination:** new `src/rn_forge/django/drf/idempotency.py`. Needs Phase 0's cache config.

```python
class CacheIdempotencyStore:
    """``rn_forge.web.IdempotencyStore`` over the Django cache."""

    def __init__(self, *, timeout: int = 86_400, cache_alias: str = "default") -> None: ...

    def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None: ...

    def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None: ...
```

**Design notes.**

- **The claim must be atomic: use `cache.add()`, not `get`-then-`set`.** This is the single most
  important line in the phase. `cache.add` is set-if-absent, which is what gives this adapter the
  race property the protocol requires (web §5.1: two concurrent first-sight requests, one wins the
  claim, both read the same row). A `get`-then-`set` implementation silently lets both execute, and
  the test below is what proves it does not.
- **Store the request hash with the claim.** `record_or_replay` computes
  `rn_forge.web.idempotency.request_hash(request_body)`; on a hit whose stored hash differs, raise
  `IdempotencyKeyReuse` (→ 409 via Phase 1's handler). This is the capability the cims version lacked
  entirely — the same key with a different body silently returned the wrong cached response.
- Cache key stays `f"idempotency:{scope}:{key}"`. `scope` exists so two endpoints cannot collide on a
  client-chosen key; say so in the docstring — it is the one non-obvious parameter.
- `timeout` is a constructor parameter with cims's 24h as the default — cims hardcodes it; the
  library must not. Same for `cache_alias` (a keyword argument, not a global or a setting).
- **Store `StoredResponse`, not an `HttpResponse`.** The old design pickled a whole response object,
  which broke on streaming responses and coupled the cache entry to Django's response class. The
  protocol's `(status, body)` pair is JSON-serializable and framework-free. A DRF view mixin
  reconstitutes the `Response`; streaming responses are simply not idempotency-cacheable, and the
  mixin should raise rather than silently skip.
- Ship the thin DRF seam alongside it: a mixin or decorator that reads the `Idempotency-Key` header,
  raises `IdempotencyKeyRequired` when it is absent on an unsafe method, and calls the store either
  side of the handler. Keep it under 40 lines; the semantics are the web package's.

**Tests.** New `tests/drf/test_idempotency.py` (`unit`): first sight returns `None`; replay after
`complete` returns `replayed=True` with the stored status and body; **the same key with a different
body raises `IdempotencyKeyReuse`**; distinct `scope` values do not collide; `timeout` and
`cache_alias` passed through (assert via a patched cache, not by sleeping); a test that patches
`cache.add` to prove it — not `cache.set` — performs the claim; the store satisfies the
`IdempotencyStore` protocol (a `runtime_checkable` isinstance check, or a Pyright assignment test if
the protocol is not runtime-checkable).

**Docs.** Fold into `docs/api/drf/index.md` or a new `docs/api/drf/idempotency.md` with a nav entry
— pick one and be consistent with what Phase 2 did.

---

### Phase 4 — Optimistic concurrency and immutability

**Source:** cims `apps/common/models.py` (`BaseModel.version` + save-increment, `ImmutableModel`)
and `apps/common/concurrency.py::enforce_version`. Depends on Phase 1's `VersionConflict` and
Phase 0's table fixture.

**Destination:**

- `src/rn_forge/django/models/concurrency.py` — the two model mixins.
- `src/rn_forge/django/drf/concurrency.py` — `enforce_version` (it parses an HTTP header and raises
  an API-shaped error; it belongs on the DRF side of the package, not in `models/`).

#### 4.1 — `VersionedModelMixin`

```python
class VersionedModelMixin(models.Model):
    """Abstract mixin adding an optimistic-concurrency ``version`` counter."""

    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True
```

`save()` increments `version` on **update only**, never on insert. Two details that will bite:

- **MRO.** The intended composition is `class Item(VersionedModelMixin, BaseModel)`. `BaseModel.save`
  (`models/base.py:174`) is keyword-only (`*, force_insert, force_update, using, update_fields`) and
  calls `full_clean` when `validate_on_save` is set. `VersionedModelMixin.save` must use the same
  keyword-only signature, must be decorated `@override`, and must call `super().save(...)` so
  `BaseModel`'s validation still runs. Test the composed class, not the mixin alone.
- **`update_fields`.** A partial save with `update_fields={"name"}` must still persist the bumped
  version — add `"version"` to `update_fields` when it is not `None`. Miss this and the increment
  silently vanishes on exactly the partial-update path optimistic concurrency exists for.

Increment in Python (`self.version += 1`) rather than with an `F()` expression: `F()` leaves the
in-memory instance stale, and the immediately-following `enforce_version` comparison in a
read-modify-write cycle would then read the wrong value.

#### 4.2 — `ImmutableModelMixin`

```python
class ImmutableModelMixin(models.Model):
    """Abstract mixin that rejects post-creation mutation and deletion."""

    IMMUTABLE_EXCLUDE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"created_by", "created_at", "updated_by", "updated_at"}
    )
```

- `save()` on an existing row re-reads the DB row and raises `DomainConflict` if any concrete field
  outside `IMMUTABLE_EXCLUDE_FIELDS` differs. Insert path is untouched.
- `delete()` always raises `DomainConflict`.
- The default exclude set matches `BaseModel`'s audit columns; a model on a different base overrides
  the class attribute. Use `get_model_meta(cls).concrete_fields` (already exported from
  `rn_forge.django.models`, see `models/_meta.py`) for the field walk rather than touching
  `_meta` directly — that indirection exists for strict-mode typing.
- The re-read is one extra query per save. Say so in the docstring; it is the cost of the guarantee.

#### 4.3 — `enforce_version` (a delegation, not an implementation)

> **Rewritten by [`web-library-plan.md`](./web-library-plan.md) §A.1.** ETag parsing, the codecs and
> the raise semantics live in `rn_forge.web.concurrency.check_precondition`.
> **Prerequisite: web plan Phase 3 has landed.**

```python
def enforce_version(
    request: HttpRequest,
    instance: VersionedModelMixin,
    *,
    required: bool = False,
    codec: ETagCodec | None = None,
) -> None:
    """Raise unless the client's precondition matches *instance*'s current version."""
```

What stays here is the Django request plumbing and nothing else:

- Read `If-Match` from `request.headers`, then fall back to a `version` key in the request body. The
  **body-key fallback is deliberately Django-only** — the web package rejects it as a weakening of the
  precondition contract (web §3.3), and this package keeps it as a documented convenience. Format the
  body value into a validator string with the codec before delegating, so there is exactly one parser.
- Delegate everything else: `check_precondition(raw_if_match, current_version=instance.version,
  entity_id=instance.pk, codec=codec or VersionETagCodec(), required=required)`. Do not parse
  weak-ETag quoting here, do not compare versions here, do not decide status codes here.
- **`VersionETagCodec` is the sensible default for this package** — `rn_forge.django.BaseModel` has no
  UUID primary key. A consumer with UUID pks passes `EntityVersionETagCodec()`.
- **Status codes changed:** a mismatch is now **412 Precondition Failed** and a missing-but-required
  header is **428 Precondition Required** (web §3.1). The old instruction here — reserve
  `VersionConflict` for a genuine mismatch, mapping to 409 — is superseded; `VersionConflict` still
  names the mismatch, it just maps to 412 in the default registry.
- **Absent header and body key, `required=False`**: pass silently. Note in the docstring that making
  the precondition mandatory is the caller's choice — now a parameter rather than a rewrite.
- Also ship `etag_for(instance)` returning the response `ETag` header value via the same codec. A
  server that enforces `If-Match` but never emits an `ETag` is asking clients to guess.

**Tests.** `tests/models/test_concurrency.py` (`integration`, needs tables): insert leaves
`version=1`; update bumps to 2; partial `update_fields` save still bumps; `validate_on_save=True`
composition still validates; immutable model rejects a field change, permits an audit-field change,
rejects delete, permits initial insert. `tests/drf/test_concurrency.py` (`unit`): each header form,
body fallback, precedence, malformed value → `MalformedPrecondition`, mismatch → `VersionConflict`,
absent + `required=True` → `PreconditionRequired`, absent + default → pass, `etag_for` round-trips
through `check_precondition`. Assert the *status codes* through Phase 1's handler in at least one
test — 412 and 428 — since that is the amendment most likely to be silently reverted.

Add the test-only models to the test module and register them with Phase 0's fixture.

**Public API.** `VersionedModelMixin` and `ImmutableModelMixin` into `models/__init__.py`'s imports
and `__all__` (sorted); `enforce_version` into `drf/__init__.py`'s.

**Docs.** A "Concurrency and immutability" section in `docs/guides/models.md`, plus API pages.

---

### Phase 5 — Two small mixins

Both are under 10 lines of source. One PR for the pair.

#### 5.1 — `OmitEmptyMixin`

**Source:** cims `apps/core/serializers.py::OmitEmptyMixin` — drops keys whose value is `None` or
`""` from `to_representation` output.

**Destination:** `src/rn_forge/django/drf/serializers/base.py`. Verified 2026-08-31: that file is 26
lines and holds `BaseModelSerializer`; `fields.py` holds field classes (`EnumChoiceField`). A
serializer mixin belongs in `base.py`.

Two things the cims version leaves implicit that the library version must not:

- **Only optional fields are stripped.** Removing a required field from a response breaks the
  contract the schema advertises. Gate on the serializer field's `required` flag, and document that
  a field explicitly declared with `allow_null=True` is still emitted — or, if that check proves
  awkward against DRF's field map, expose `OMIT_EMPTY_FIELDS: ClassVar[frozenset[str] | None] = None`
  meaning "all optional fields" and let a consumer narrow it. Pick one and write down why.
- **Empty means `None` or `""` only.** Not `0`, not `False`, not `[]`, not `{}`. State this in the
  docstring — it is the first thing someone will get wrong when they extend it.

Export from `drf/serializers/__init__.py`.

**Tests.** Extend `tests/drf/serializers/test_base.py`: optional empty stripped; required empty
retained; `0`/`False`/`[]` retained; composes with `BaseModelSerializer` without disturbing the
`BASE_MODEL_FIELDS` read-only block.

#### 5.2 — `PermissionByMethodMixin`

**Source:** cims `apps/core/views.py::PermissionByMethodMixin` — maps an HTTP method to the
permission classes required for it.

**Destination:** `src/rn_forge/django/drf/views/mixins.py`, alongside `RequestAccessViewMixin`,
`ExceptionContextViewMixin`, `ModelFilterViewMixin`, `AuditFieldsViewMixin` (190 lines; the
`__all__` there is sorted — keep it that way).

```python
class PermissionByMethodMixin:
    """Select DRF permission classes per HTTP method."""

    PERMISSION_CLASSES_BY_METHOD: ClassVar[Mapping[str, Sequence[type[BasePermission]]]] = {}
```

Override `get_permissions()`: look up `self.request.method` (upper-cased), fall back to the view's
own `permission_classes` when the method is not in the map. **Do not silently allow an unmapped
method** — falling back to the view default is the safe behaviour; falling back to "no permissions"
is a security bug. Say which one it does in the docstring.

Note the relationship to the existing `DRFViewsSettings.permission_action_map` setting
(`settings.py:83`), which maps *actions* to permissions — these are two different axes and both can
be active. Add one sentence to the docstring distinguishing them so a reader does not assume one
supersedes the other.

**Tests.** Extend `tests/drf/views/test_mixins_and_base.py` (`unit`): mapped method uses its
classes; unmapped method falls back to `permission_classes`; empty map behaves exactly like the
plain view.

---

### Phase 6 — Readiness view and the Django settings guard

**Source:** cims `apps/common/views.py::readyz` and `config/settings/production.py`'s
`required_environment` fail-fast block.

#### 6.1 — `readiness_view` factory (a view over `run_checks_sync`)

> **Rewritten by [`web-library-plan.md`](./web-library-plan.md) §A.1.** Check aggregation, the
> four-value status, exception capture and the 503 rule live in `rn_forge.web.health`. This phase is
> the view wrapper. **Prerequisite: web plan Phase 6 has landed.**

**Destination:** `src/rn_forge/django/views.py`, joining `index_view`, `healthcheck_view`,
`debug_request_view` (the module is already dependency-light and URLconf-includable — this fits).

```python
def readiness_view(
    checks: Mapping[str, Check],
    *,
    required: Collection[str] = (),
) -> Callable[[HttpRequest], JsonResponse]:
    """Build a readiness view that reports one entry per dependency check."""
```

- A **factory**, not a view: consumers write
  `path("readyz", readiness_view({"database": ping_db, "cache": ping_cache}, required=["database"]))`
  in their URLconf. This is what removes cims's module-level `SERVICE_BUS_REQUIRED` flag.
- The body of the returned view is `report = run_checks_sync(checks, required=required)` followed by
  `JsonResponse(report.as_dict(), status=report.http_status)`. **Nothing else.** Do not catch
  exceptions per check here (the web runner already wraps every check), do not re-derive the 503 rule
  (`HealthReport.http_status` carries it), and do not coerce `bool` returns (the runner does).
- `Check` is `rn_forge.web.health.Check`, so a check may return `bool` or a `CheckResult`, and a
  four-value status (`pass`/`warn`/`fail`/`skipped`) reaches the body. The response shape is the web
  package's `HealthReport`, **not** cims's `{"status": "ok"|"degraded", ...}` — one readiness body
  across every app in the kit is the point, and cims is being rewritten anyway.
- `run_checks_sync` **raises** if handed an async check. Django views are sync; that is the correct
  behaviour and worth one test rather than a workaround.
- Decorate with `@require_GET`, matching every other view in the module.
- Empty `checks` → 200 with an empty `checks` object, not an error.

Add to `views.py`'s `__all__` (sorted) and to `docs/api/urls-and-views.md`.

#### 6.2 — Django-flavoured environment guard

The commons plan's Phase 7 adds `Environment.require(*names) -> dict[str, str]` and
`Environment.forbid(name, *forbidden, message=None)` to `rn_forge/commons/utils.py`, raising
`AppException`. **This phase adds only the thin Django wrapper**, in
`src/rn_forge/django/utils.py`:

```python
def require_settings(*names: str) -> None:
    """Raise ``ImproperlyConfigured`` if any named Django setting is unset or blank."""


def require_environment(*names: str) -> dict[str, str]:
    """Delegate to ``Environment.require``, re-raising as ``ImproperlyConfigured``."""
```

`ImproperlyConfigured` is what Django's own machinery and every deployment runbook expect at
startup; `AppException` is what commons must raise to stay Django-free. The wrapper is the seam.
Aggregate all missing names into one message (same requirement as the commons side) — a deployment
should surface every misconfiguration in one run.

**Ordering.** This half depends on commons Phase 7 having landed. If it has not, either do Phase 6.1
alone and defer 6.2, or implement `require_environment` against `os.environ` directly and swap the
body to delegate later — say which one you did in the PR.

**Tests.** `tests/test_views.py` additions (`unit`): all-pass 200; non-required fail 200 with the
failure recorded and the overall status degraded; required-fail 503; raising check captured with its
message rather than 500ing; `warn` and `skipped` surfaced at 200; an async check raises; empty checks
200. Keep these thin — the aggregation semantics are tested in the web package, and duplicating that
suite here just makes both harder to change.
`tests/test_utils.py` additions: each guard's raise/pass paths with `monkeypatch.setenv/delenv` and
`override_settings`, and the several-missing-names-in-one-message case.

---

## Part B — New modules

### Phase 7 — Correlation-ID (WSGI) middleware

> **Rewritten by [`web-library-plan.md`](./web-library-plan.md) §A.1.** The ContextVar, the getters
> and the log processor live in `rn_forge.web.context`; this package keeps only the WSGI middleware,
> which the ASGI one in web Phase 7 cannot serve. **Prerequisite: web plan Phase 1 has landed.**

**Source:** cims `apps/common/middleware.py::RequestIdMiddleware`. Only the request-ID half — see
"Things deliberately NOT extracted" on `AuditContextMiddleware`.

**Destination:** new `src/rn_forge/django/middleware.py` (no such module exists today).

```python
class CorrelationIdMiddleware:
    """Assign and propagate a correlation ID for every request."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponseBase],
        *,
        log: Callable[[str, Mapping[str, Any]], None] | None = None,
        header: str = DEFAULT_CORRELATION_HEADER,   # "X-Correlation-ID"
    ) -> None: ...
```

- **Do not define a ContextVar here.** Import `rn_forge.web.context`'s. Two ContextVars for one
  concept is exactly the duplication this restructuring exists to prevent — Phase 1's handler and any
  consumer log processor must read the same variable this middleware writes.
- **The default header is now `X-Correlation-ID`**, not `X-Request-ID`. That default existed only to
  preserve a cims call site, and cims is being rewritten; one header name across every app in the kit
  is the point. `header=` stays for anyone fronted by infrastructure that stamps something else.
- Keep the class name `CorrelationIdMiddleware` to match `rn_forge.web.asgi`'s. Nothing ships under
  the old name — this package has no released consumer of it.

Behaviour: read the inbound header or generate one with `rn_forge.web.context.new_correlation_id()`;
bind it with **`bind_correlation_id()`, the context manager that resets on exit** — this is the WSGI
case web §1 describes, where a worker thread genuinely is reused and a leak across requests is the
classic bug (the ASGI middleware deliberately does *not* reset; do not copy that half here); bind it
to `request` as an attribute too; call the injected `log` with a `request.complete` event carrying
`method`, `path`, `status`, `duration_ms`, `correlation_id`; echo the header on the response.

**Design notes.**

- `log` is injected per Convention 1, defaulting to a thin wrapper over
  `AppLogger.get_logger(__name__).info` that formats the mapping into the `{}`-style message form
  this repo uses. That default is what makes it usable out of the box; the parameter is what makes
  it adoptable by a structlog consumer.
- **Re-export `rn_forge.web.context`'s accessors** from this module for discoverability
  (`get_correlation_id`, `correlation_log_processor`), but do not wrap or shadow them.
- Django's middleware factory contract means `__init__` is called once with `get_response`; the
  keyword arguments above are for programmatic construction and tests. Provide a
  `make_request_id_middleware(*, log=None, header=...)` factory returning the middleware class or a
  configured callable, so it can be named in `MIDDLEWARE` with non-default options — or document
  subclassing as the supported customization path. Pick one; do not ship both.
- Do not read the ID from `traceparent` or any other header by default. A consumer with a different
  convention passes `header=`.

**Tests.** New `tests/test_middleware.py` (`unit`): inbound header preserved; absent header generated;
header echoed on the response; `log` callable invoked once with all expected keys;
`get_correlation_id()` readable from inside a view and back to `None` afterwards (the reset that the
ASGI side deliberately omits); ContextVar isolation across two sequential requests; a custom `header=`
honoured on both read and echo.

**Docs.** New `docs/api/middleware.md` + nav entry; a short "wiring it into `MIDDLEWARE`" block in
`docs/guides/quickstart.md`.

---

### Phase 8 — Sequence-backed code generator

**Source:** cims `apps/common/identifiers.py` (`generate`, `ensure_at_least`).
**Destination:** new `src/rn_forge/django/models/sequences.py`.

This is the highest-risk phase in Part B, entirely because of what the test suite cannot prove
(Phase 0's sqlite note). Read that before starting.

```python
class SequenceCounter(models.Model):
    """Concrete counter table backing the non-PostgreSQL sequence path."""

    name = models.CharField(max_length=100, unique=True)
    value = models.PositiveBigIntegerField(default=0)


class SequenceGenerator:
    """Allocate gap-free, human-readable codes from a named database sequence."""

    def __init__(
        self,
        name: str,
        *,
        prefix: str = "",
        formatter: Callable[[str, int], str] | None = None,
    ) -> None: ...

    def generate(self) -> str: ...
    def ensure_at_least(self, value: int) -> None: ...
```

**Design notes.**

- **`SequenceCounter` ships concrete, not abstract** — a deviation from the survey. An abstract
  counter would force every consumer to declare a subclass and a migration for a table with no
  domain content, and `SequenceGenerator` would then need to be told which model to use. A concrete
  model in this package with its own migration is what an app already gets by adding
  `rn_forge.django` to `INSTALLED_APPS`. **But note what that implies here:** verified 2026-08-31,
  this package ships **no migrations directory anywhere** — the `rn_forge_django_auth` app
  (`auth/apps.py`) has no migrations, and the test suite builds its tables with
  `connection.schema_editor()` rather than by migrating. So a concrete `SequenceCounter` makes this
  phase the point where "this package ships migrations" becomes true for the first time, which
  changes what installing it implies for every consumer. That is a real decision, not a detail:
  make it explicitly in the PR. If shipping migrations is not acceptable, fall back to the survey's
  abstract-model design (consumer declares the subclass and owns the migration, `SequenceGenerator`
  takes the model as a constructor argument) and record why.
- The default formatter is `f"{prefix}{value:06d}"` when a prefix is given, else `str(value)`.
  cims's `PO-2026-0001` shape is a **caller-supplied formatter**, not a library format — the year
  segment in particular is domain policy.
- `generate()` uses a real PostgreSQL sequence when `connection.vendor == "postgresql"`
  (`CREATE SEQUENCE IF NOT EXISTS` + `nextval`), else `select_for_update()` on the `SequenceCounter`
  row inside a transaction. Validate `name` against a strict pattern (`[a-z][a-z0-9_]*`) before
  interpolating it into the DDL — sequence names cannot be bound as query parameters, so this is the
  only thing standing between the caller and SQL injection. Do this even though callers are
  expected to be trusted.
- `ensure_at_least(value)` raises the sequence/counter floor for backfill and import scenarios, and
  is a no-op when the current value is already higher.

**Tests.** New `tests/models/test_sequences.py`: sqlite counter path end-to-end (`integration`);
formatter default and override (`unit`, no DB); `ensure_at_least` raise and no-op; invalid sequence
name rejected (`unit`); concurrent allocation under sqlite **cannot** be tested meaningfully — do
not write a test that appears to prove it. Add a `pytest.mark.integration` PostgreSQL test only if a
Postgres service is actually available to the suite; as of 2026-08-31 it is not, so record the
PostgreSQL path as verified-in-cims-only in the module docstring and in the PR.

**Docs.** `docs/api/models.md` addition + a "Generating human-readable codes" section in
`docs/guides/models.md` that states the sqlite-vs-PostgreSQL split plainly.

---

### Phase 9 — JWKS bearer authentication

**Source:** cims `apps/common/auth.py` (`EntraAuthentication`, `Principal`,
`EntraAuthenticationScheme`).
**Destination:** new `src/rn_forge/django/auth/jwt/oidc.py`. New `oidc` extra.

**Amended by the web plan (§A.1): this phase is now a *binding*, not a design.** Three things move out
of it, and what is left is the DRF plumbing:

- **`Principal` is `rn_forge.web.auth.Principal`** (web §10.2), not a type defined here. cims's is
  prior art for the *fields*; the shared one is what a FastAPI service also returns, which is the
  whole point. `claims_to_principal` returns it, and its signature stops being `-> Any`.
- **Token verification comes from the commons `auth/` module** (web plan §A.2) — JWKS fetch, caching,
  rotation, signature and claims validation. This module does not implement any of it; it calls it.
  **This phase is blocked on that module and on web Phase 10.**
- **The failure behaviour is web §10.4's, not DRF's.** DRF's stock `BaseAuthentication` raises
  `NotAuthenticated`/`AuthenticationFailed`, which render as DRF's own `{"detail": ...}` body with a
  `WWW-Authenticate` header of DRF's own construction. Both are wrong against the shared contract:
  the body must be `application/problem+json` via Phase 1's handler, and the challenge must be RFC
  6750 §3's `error=`/`error_description=` form built by `web.auth.challenge_header`. Override, do not
  inherit. Getting this wrong is the single most likely way this package ends up with two error
  formats.

**Also ship basic auth** (RFC 7617) in `auth/basic/`, producing the same `Principal` and the same 401
challenge, explicitly documented as local-development and simple-internal-deployment only — the
fastapi plan's Phase 6b ships its twin, and the conformance table (Phase 13) covers both.

**Scope/role checks** use `web.auth.Requirement` through a DRF permission class, so a requirement
expressed once evaluates identically on both stacks.

This is a *different mechanism* from the existing `auth/jwt/authentication.py`, which wraps
simplejwt-issued tokens against a local `User`. Here the token is issued externally and verified
against a remote JWKS endpoint, with no local user. Same sub-package, separate module; do not try to
merge them.

```python
class JWKSBearerAuthentication(BaseAuthentication):
    """Authenticate a bearer token against a remote OIDC JWKS endpoint."""

    jwks_url: ClassVar[str]
    audience: ClassVar[str]
    issuer: ClassVar[str]
    algorithms: ClassVar[Sequence[str]] = ("RS256",)
    cache_timeout: ClassVar[int] = 86_400

    def claims_to_principal(self, claims: Mapping[str, Any]) -> Any: ...
```

**Design notes.**

- **The IdP is a parameter, not a hardcode.** Entra's discovery URL
  (`https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`) becomes a documented recipe for
  constructing `jwks_url`, never a constant in this module. The class must work unchanged against
  Auth0, Okta, Keycloak, or any OIDC IdP.
- **`claims_to_principal` is the reusability hook.** cims's Walgreens-specific app-role extraction
  becomes an override point. Ship a minimal default `Principal` dataclass (subject, name, scopes,
  raw claims) using `DataclassMixin` from commons so it serializes consistently, but expect real
  consumers to override — cims keeps its own `Principal`.
- **JWKS caching.** Fetch keys, match on the token's `kid`, cache the key set in Django's cache
  under a key derived from `jwks_url`, honour `cache_timeout`. On an unknown `kid`, refetch **once**
  (key rotation) before failing — a cached key set outliving a rotation is the failure mode people
  actually hit in production. Bound that refetch so a token storm cannot hammer the IdP.
- Verify `exp`, `aud`, `iss`, and the signature. Raise DRF's `AuthenticationFailed` for every
  verification failure with a generic message; log the specific reason at debug level. Do not leak
  which check failed to the client.
- `Authorization: Bearer <token>` only. No header returned by `authenticate_header` other than
  `Bearer`.
- Whether to configure via class attributes (subclass per IdP, matching DRF convention and this
  package's existing auth classes) or constructor arguments: **class attributes**, because
  `DEFAULT_AUTHENTICATION_CLASSES` names a class, not an instance. A settings-facade block
  (`AUTH.OIDC`) is a reasonable follow-up but is **not** in this phase — keep the surface small
  until a second consumer exists.
- `JWKSBearerAuthenticationScheme` (the drf-spectacular `OpenApiAuthenticationExtension`) is **out of
  scope** — this package has no drf-spectacular dependency and Phase 12 explains why it stays a
  documented recipe.

**Tests.** New `tests/auth/jwt/test_oidc.py` (`unit`), gated with
`pytest.importorskip("jwt")`: locally-generated RSA keypair, hand-built JWKS document served through
a patched fetch; valid token authenticates; expired, wrong-audience, wrong-issuer, wrong-signature,
malformed-header, and missing-header cases all fail with `AuthenticationFailed`; JWKS cache hit
avoids a second fetch; unknown `kid` triggers exactly one refetch; `claims_to_principal` override is
invoked and its return value lands on `request.user`. Never call a real IdP from a test.

**Docs.** New `docs/api/auth/oidc.md` + nav entry under `API Reference > Auth`; a section in
`docs/guides/auth.md` with the `jwks_url` recipes for Entra, Auth0 and Okta side by side.

---

## Part C — Gated subsystems

### Phase 10 — GATED: outbox/inbox messaging

This is the best-designed subsystem in cims and the biggest single lift in this plan. Treat it as
one cohesive piece of work, not four independent extractions.

#### 10.1 — The gate

**Do not start this phase until all three are true.** Write the answers down in the PR before
writing code:

1. **A concrete consumer is committed.** Not "cims might adopt it" — an actual service that will
   depend on the extracted version. A transactional outbox designed against exactly one caller will
   encode that caller's delivery semantics, and unwinding that later is a breaking change to
   database tables, which is the most expensive kind.
2. **The locking path can be exercised somewhere.** The relay's correctness *is*
   `select_for_update(skip_locked=True)`. sqlite supports neither (Phase 0). Either the suite gains
   a PostgreSQL `integration` job, or you accept that the core of this subsystem ships with no
   automated proof — which for a component whose failure mode is silent duplicate publishing is not
   an acceptable answer. Decide before starting, not after.
3. **The envelope question is settled.** The relay needs an `envelope_builder`. The CloudEvents
   builder was deferred by the commons plan precisely because it had no consumer; this subsystem is
   that consumer. Either build it in commons first, or confirm that consumer-supplied builders are
   the permanent design.
4. **Commons Phase 8b has landed** (`rn_forge.commons.integration.messaging`: `MessageBus`,
   `InMemoryMessageBus`, `HandlerRegistry`). This phase now consumes those rather than defining
   them — see §10.2.

If the gate fails, stop and record why. The abstract models are the part that is expensive to get
wrong; nothing else here is urgent.

#### 10.2 — If the gate passes

**Destination:** new `src/rn_forge/django/messaging/` package. No new extra (see the dependency
section); the consumer adds it to `INSTALLED_APPS`.

- **`models.py`** — `AbstractOutboxMessage`, `AbstractInboxMessage`, abstract, subclassed by the
  consuming app the same way `BaseModel` is. **Preserve the `(published_at, occurred_at)` index on
  the outbox table** — that composite is what makes the relay's polling query cheap, and it is the
  single most consequential line to carry over verbatim. Do not add `status` or camelCase columns
  (Convention 3).
- **`bus.py` — moved out of this package.** Per
  [`web-library-plan.md`](./web-library-plan.md) §A.2, the `MessageBus` protocol, `InMemoryMessageBus`
  and `HandlerRegistry` now live in **`rn_forge.commons.integration.messaging`** (commons plan Phase 8b), so
  `rn-forge-azure` can implement a Service Bus adapter without depending on Django. This package
  **imports** them; it defines none of them. Messaging is not HTTP-shaped and a worker needs it, which
  is why commons rather than `rn-forge-web` is the destination.
- **`relay.py`** — a task **factory**, not a task:

  ```python
  def make_outbox_relay(
      outbox_model: type[AbstractOutboxMessage],
      bus: MessageBus,
      *,
      envelope_builder: Callable[[AbstractOutboxMessage], Mapping[str, Any]],
      batch_size: int = 100,
      on_lag_observed: Callable[[float], None] | None = None,
      log: Callable[[str, Mapping[str, Any]], None] | None = None,
  ) -> Callable[[], int]:
      """Build a callable that claims, publishes and marks one batch of outbox rows."""
  ```

  Returns a plain callable the consumer wraps in their own `@shared_task` — that is what keeps
  Celery out of this package's dependencies. Return the number of messages published so a caller can
  drain in a loop. Claim with `select_for_update(skip_locked=True)` inside `transaction.atomic()`.
  `on_lag_observed` and `log` are the Convention 1 and 2 hooks.
- **`consumer.py`** — `process_event(event, registry, inbox_model)` implementing
  dedup-by-`message_id`, dispatch and status recording against the Django ORM. `HandlerRegistry`
  itself comes from `rn_forge.commons.integration.messaging` (it is a plain dict-backed registry with no ORM
  involvement); only the inbox-table interaction is Django's. Re-raise after recording a failure so
  the broker can dead-letter — swallowing there turns a visible failure into silent data loss.

**Tests.** New `tests/messaging/`: no `test_bus.py` — the bus and registry contracts are tested in
commons; `test_consumer.py` (dedup on replay, unknown message type, handler failure recorded *and*
re-raised, `integration`); `test_relay.py` (batch size honoured, published rows marked, empty batch is a no-op,
`envelope_builder` invoked per row, `integration`) — with the locking behaviour covered only if the
gate's item 2 produced a PostgreSQL job.

**Explicit non-goals.** No `AzureServiceBus`, no Azure Blob claim-check, no `run_consumer` /
`resubmit_dlq` management commands. If a second cloud-messaging consumer appears, *that* is the
trigger to design a pluggable adapter interface — not now.

---

### Phase 11 — GATED: Celery integration

Unlike everything else here, this is **not extracted from cims** — cims's Celery usage is stock
`@shared_task`. This phase is net-new convenience code.

#### 11.1 — The gate

**Build this only if wiring Phase 10's relay factory into a real Celery app proved annoying in
practice.** A `make_app` helper saves six lines of boilerplate that every Celery user has already
written once; a `RETRYABLE_TASK_KWARGS` dict saves three. Neither justifies a new optional
dependency on its own, and a thin wrapper over someone else's bootstrap is exactly the kind of
facade that goes stale. If Phase 10 did not happen, this phase does not happen.

#### 11.2 — If the gate passes

**Destination:** new `src/rn_forge/django/celery.py`, new `celery` extra.

```python
def make_app(
    name: str,
    *,
    config_source: str = "django.conf:settings",
    namespace: str = "CELERY",
    autodiscover: bool = True,
) -> Celery: ...


RETRYABLE_TASK_KWARGS: Final[dict[str, Any]] = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_kwargs": {"max_retries": 5},
}
```

`RETRYABLE_TASK_KWARGS` stays a plain dict consumers spread into `@shared_task(**...)` — not a
decorator wrapper. Import `celery` lazily or guard it so `import rn_forge.django` still works
without the extra installed.

Do **not** build `make_outbox_relay_task` speculatively; it only exists if manual wiring proved
annoying, which is the same gate as above.

**Tests.** New `tests/test_celery.py`, gated with `pytest.importorskip("celery")`: `make_app`
returns a `Celery` whose config reflects the namespace; `autodiscover=False` respected; a snapshot
assertion on `RETRYABLE_TASK_KWARGS`'s exact shape, since consumers spread it directly and a silent
change to it changes their retry behaviour.

---

### Phase 12 — Schema and casing, as shipped code

**Amended by the web plan (§A.1): this phase was docs-only and is now code.** The original reasoning
was that the package has neither dependency and should not acquire them speculatively. That holds for
a recipe nobody is obliged to follow; it does not hold once `api-conventions.md` makes camelCase and
the OpenAPI component names **normative for both frameworks**. `rn-forge-fastapi` enforces its half in
code (its Phase 2 `WireModel` and Phase 3 `operationId` function); a Django half that is a page of
copy-pasteable settings is not a matching guarantee, and the asymmetry would show up as two different
generated clients.

**New dependencies**, both behind an `openapi` extra so a consumer that does not publish a schema
carries neither: `djangorestframework-camel-case` and `drf-spectacular`. Verify both are currently
maintained in this phase's first step and record the result — the workspace dependency policy applies
here as everywhere.

**Deliverables:**

1. **Casing wired through the settings facade.** `CamelCaseJSONRenderer` / `CamelCaseJSONParser` as
   the defaults, switchable off for a consumer that has a reason, following the `PaginationSettings`
   pattern exactly. The rule is camelCase out, **both spellings accepted in** — matching the FastAPI
   side's `populate_by_name=True`, so an internal caller posting `snake_case` works against either
   stack.
2. **A DRF serializer mirror of `ProblemDetail`,** plus `Page`, `CheckResult` and `HealthReport`.
   This is the Django counterpart of the fastapi plan's Phase 2 pydantic mirrors and it exists for
   the same reason: drf-spectacular builds `components/schemas` from serializers, so without a
   serializer the shared error type never reaches the Django schema — the exact gap fastapi Phase 3
   exists to close on its side. Each mirror gets the round-trip test its pydantic twin gets:
   `Mirror(data=asdict(dataclass_instance)).is_valid()` and `.data == asdict(...)`.
3. **`SPECTACULAR_SETTINGS` shipped as a dict this package exports,** not as a snippet to copy:
   `OAS_VERSION` pinned to **3.1.0** to match FastAPI, `CAMELIZE_NAMES: True`, the
   `djangorestframework_camel_case.contrib` postprocessing hook, the shared component names, and the
   `operationId` convention from `api-conventions.md`. An application spreads it into its own
   settings and overrides what it must.
4. **The nested-`DictField` gotcha**, which was the original reason this page existed and is now the
   reason a piece of code exists: global camelCase parsing recurses into opaque `DictField`/
   `JSONField` values and mangles keys that must stay verbatim. cims works around it in
   `apps/core/serializers.py::normalize_line`. **Ship `RawPassthroughField`** in
   `rn_forge/django/drf/serializers/fields.py` rather than documenting the workaround: making casing
   the library's default makes this the library's problem, and the "wait for a second consumer" test
   the original phase set is met the moment casing stops being opt-in.
5. **`JWKSBearerAuthenticationScheme`** — the drf-spectacular security-scheme registration for
   Phase 9's authenticator, so the schema declares how to authenticate. Previously listed as an
   omission with a pointer to a recipe; with this phase shipping code it belongs here.
6. A `docs/guides/openapi.md` covering what an application still has to do, which should be close to
   nothing beyond spreading the settings dict.

---

### Phase 13 — The conformance driver

~15 lines, and the only test in this package that can fail because of something `rn-forge-fastapi`
does. It is the Django half of the pair; the FastAPI half is that plan's Phase 6c, and **both must
exist for either to mean anything.**

Build a minimal Django/DRF application wired with everything this plan ships — the problem handler,
cursor pagination, the idempotency store, `enforce_version`, the readiness view, the correlation
middleware and the Phase 9 authenticator — run every case in `rn_forge.web.conformance.CASES` through
the DRF test client, redact with `web.conformance.redact`, and assert equality against the table.

- **Assert against the table, never against FastAPI's output.** Two stacks agreeing on the wrong
  thing is not conformance.
- **A case this package cannot satisfy is a finding, not a skip.** Either an adapter is missing, or
  the case encodes a decision Django cannot honour — which is a web-plan change, raised there. A
  `pytest.skip` here silently removes the guarantee.
- Mark it `integration` if it needs the DB; the idempotency and concurrency cases will.

---

## Deferred — do not build these yet

- **Claim-check pattern** (cims `apps/messaging/claim_check.py`). Threshold-based payload
  externalization plus a SHA-256 integrity check. The logic is generic; the only concrete storage
  backend is Azure Blob, and designing a storage `Protocol` from one example reliably produces the
  wrong abstraction. Also note it is commons-shaped, not Django-shaped — if it is ever built it goes
  in `rn_forge/commons/claim_check.py`, and the commons plan already records it as deferred there.
- **Cloud messaging adapters** (Azure Service Bus, and any S3/GCS/SQS equivalent). Trigger: a second
  cloud backend actually in view.
- **`RawPassthroughField`** — see Phase 12.
- **A settings-facade block for OIDC** (`AUTH.OIDC`) — see Phase 9. Trigger: a second consumer.

---

## Final checklist before calling this done

- [ ] `uv sync --all-extras && uv run pytest packages/rn-forge-django` green
- [ ] `uv run pyright` clean (strict; `src/` only — no new file-level suppressions added)
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run --directory packages/rn-forge-django --group docs mkdocs build --strict` clean
- [ ] Every new public symbol re-exported from its **sub-package** `__init__.py`, `__all__` sorted
      (Convention 4 — the top-level `rn_forge/django/__init__.py` stays empty)
- [ ] `import rn_forge.django` succeeds with **no** optional extras installed (guards Phase 9's and
      Phase 11's optional imports)
- [ ] Existing behaviour unchanged: `tests/drf/test_exceptions.py` and the pre-existing
      settings-reload tests pass untouched
- [ ] Every new test carries a `unit` or `integration` marker; full suite passes under
      `pytest-randomly` twice with different seeds
- [ ] `mkdocs.yml` nav updated for every new page (pagination, idempotency, middleware, oidc,
      api-conventions, plus messaging/celery if Part C shipped)
- [ ] Version bumped to `0.3.0` and released as the tag `rn-forge-django-v0.3.0` (kiln D46 — there is
      no PyPI release), with the installation guide documenting the `git+…@tag` form per extra
- [ ] `uv run lint-imports` green: `rn_forge.django`'s runtime surface imports neither `rn_forge.cli`,
      `rn_forge.tooling`, Typer nor Jinja, and never imports `rn_forge.fastapi`
- [ ] `.importlinter` carries `rn_forge.web` in `root_packages` with the two contracts from the web
      plan's alignment §2, landed in the same change as the `rn-forge-web` dependency
- [ ] No Typer command surface was added to this package (alignment §6 — the declared `[cli]` surface
      belongs to `python-app`/`python-tool` repos; Django keeps `manage.py`)
- [ ] `CLAUDE.md`'s `rn-forge-django` bullet updated — its extras list and architecture notes both
      change if Phase 9 or Part C lands
- [ ] `CursorPagination` is the standard class and emits the AIP-158 envelope over the shared codec;
      the page-number class is named `LegacyPageNumberPagination`; `pageSize` is clamped, never
      rejected with a 400
- [ ] The `reverse`-flag decision (web §4.3) is made and recorded in **both** plans
- [ ] camelCase renderer/parser wired as the default through the settings facade, with both spellings
      accepted on input; `RawPassthroughField` ships and the nested-`DictField` case is tested
- [ ] The DRF schema mirrors round-trip against the `rn_forge.web` dataclasses, and the emitted schema
      is OpenAPI **3.1.0** with the shared components named exactly as the FastAPI side names them
- [ ] Phase 9 returns `rn_forge.web.auth.Principal`, renders 401/403 as `problem+json` through Phase
      1's handler, and builds its challenge with `web.auth.challenge_header` rather than inheriting
      DRF's — asserted by a test, since inheriting DRF's default is the silent failure mode
- [ ] Basic auth ships and is documented as local/simple-deployment only
- [ ] Phase 13's conformance driver runs every case in `rn_forge.web.conformance.CASES` with no skips
- [ ] Phase 10 and Phase 11 gate outcomes recorded (built, or abandoned with the reason written down)
- [ ] The Phase 8 migrations decision recorded, whichever way it went
- [ ] Nothing committed or pushed — leave the working tree for review

## Not in this plan (deliberately deferred)

- **`rn-forge-commons` changes.** Out of scope. Three commons phases are prerequisites for phases
  here (Phase 7 environment guards → Phase 6.2; Phase 8b messaging → Phase 10; Phase 8 resilience →
  nothing here directly, but it is the other half of the same cims survey). See
  [`commons-upgrade-plan.md`](./commons-upgrade-plan.md).
- **`rn-forge-web` changes.** Also out of scope, and now a hard prerequisite: Phases 1, 3, 4.3, 6.1
  and 7 cannot start until the corresponding web-package phase has landed. See
  [`web-library-plan.md`](./web-library-plan.md) and the ordering in
  [`README.md`](./README.md).
- **Lowering the Python floor.** Dropped as a prerequisite entirely — see the Python-floor note
  above. If a future consumer needs it, it is a project-wide decision with its own gate.
- **`drf/views/transfer.py` vs `django-import-export`+`tablib`.** Real overlap, ~1,200 lines, needs
  its own plan.
- **The `RequestUtils` name collision** between `django/utils.py:40` and `django/drf/utils.py:49`.
  Breaking to fix; needs its own plan.
- **cims's adoption of any of this.** cims is being respecified and reimplemented; that work happens
  in its own repo, against whatever version of these APIs ships. Treat its current code as **prior
  art, not a compatibility constraint** — where the survey found a weaker design, fix it here rather
  than preserving the call site. What this plan owes the rewrite is documentation good enough to spec
  against (see the web plan's Phase 9).
