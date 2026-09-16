# `rn-forge-fastapi` — new package plan

Scope: a **new** workspace package, `packages/rn-forge-fastapi` (import path `rn_forge.fastapi`),
holding the FastAPI/Starlette adapter layer over [`rn-forge-web`](./web-library-plan.md). It is the
mirror of [`django-upgrade-plan.md`](./django-upgrade-plan.md)'s Part A: the same seven wire concerns,
wired into the other framework.

**This package was deferred, and its trigger has fired.** The web plan deferred it with the condition
*"the first FastAPI application rewritten on `rn-forge-web`"*, on the reasoning that an adapter API
should be fixed against a real rewrite rather than against code being deleted. Two now exist:

- **intellibuild** — the successor to intellibench, a kiln **`python-web-app`** repo with
  `framework = fastapi` and `frontend = angular`, its frontend built as a separate package (owner
  decision 2026-09-12, which replaced `python-web-api`; rebuilt, not migrated, per D39). It is now a
  standalone plan in kiln and does not gate kiln's releases.
- **`golden/python-web-api`** — kiln's hand-authored, runnable golden repo for that archetype, which
  under kiln **ADR-0005** is written and reviewed *before* the application that copies it, and before
  any generator code exists. It is the acceptance test for this package, and it is why this plan has
  to exist rather than letting intellibuild grow its own adapter layer.

The web plan's own warning is the reason to act now rather than after intellibuild ships: *"that layer
is exactly what would get duplicated by the next app."*

Three sources feed this plan, and it is self-contained:

- **The FastAPI extraction candidates** recorded in [`web-library-plan.md`](./web-library-plan.md) →
  "FastAPI extraction candidates (for the future `rn-forge-fastapi` plan)", harvested from the
  intellibench survey of 2026-08-31 (`apps/api/src/intellibuild_api/*`) while it was fresh. That
  section is the inventory this plan turns into phases; it is not repeated here beyond what each phase
  needs.
- **`rn-forge-web`** as the web plan specifies it — every module here is an adapter and none of them
  re-decides a wire shape.
- **The pykit workspace and kiln's canon** as they stand on 2026-09-10, for scaffold conventions, the
  library graph and the release contract.

**Start from [`README.md`](./README.md)** — it carries the execution order across all five plans.
This package is blocked on web Phases 1–8 in their entirety; see Phase 0.

## Implementation status (2026-09-12, updated 2026-09-13)

**Phases 0–7, 6b and 6c are implemented and committed (`3e80dbd`); Phase 8 and the release tag are
open, and both follow kiln's in-progress work.** The package, its README, docs site and tests are at
`packages/rn-forge-fastapi`; the checklist at the end marks each item.

**Updated 2026-09-16** — decision 0.3's `test_fastapi_*` basenames are gone: the root
`pyproject.toml` now sets `--import-mode=importlib` in `[tool.pytest.ini_options]`, which already
resolves same-named test modules across packages (django and web both have `test_models.py`-style
duplicates today). The prefix no longer does anything; `rn-forge-fastapi`'s test modules were
renamed to match their `rn-forge-web` counterparts (`test_auth.py`, `test_conformance.py`, etc.),
and django's `tests/test_django_conformance.py` was renamed to `tests/test_conformance.py` for the
same reason.

**Updated 2026-09-13** — three statements below were true on 2026-09-12 and no longer are:

- The commons `auth/` module exists (`rn_forge/commons/integration/auth.py`). Phase 6b's binding
  needed no change: an application puts the commons verifier behind `rn_forge.web.Authenticator`.
- `rn-forge-django` has its conformance driver (`tests/test_conformance.py`), so step 14a is
  done and the two drivers together now prove the stacks agree.
- `run_checks` has a per-check timeout, and `health_router(timeout=...)` passes it through; the
  timeout test is written (`test_a_hung_required_check_times_out_as_503`).

Decisions recorded while implementing, each with its reason in the package README or the module
docstring named:

- **0.1 — the tag is pinned before it exists.** `rn-forge-web-v0.1.0` is not cut; the pin names the
  tag it will get, the same convention web's own `rn-forge-commons-v0.5.0` pin follows. Cutting it
  is web plan step 12 and needs a decision to push.
- **0.2 — `rn_forge.fastapi` is kept.** Reasons in the README's "The namespace decision";
  `tests/test_namespace.py` asserts the disjoint `__path__`.
- **0.3 — no `tests/__init__.py`.** `CLAUDE.md` forbids it: it collides with django's `tests`
  package from the root. (Originally this also forced `test_fastapi_*` basenames to dodge
  same-named modules in `rn-forge-web`; superseded 2026-09-16 below.)
- **`rn-forge-commons` is not a declared dependency** — nothing imports it directly.
- **Phase 1 registers a handler per registry type**, not one on `Exception`: Starlette's
  `ServerErrorMiddleware` re-raises after rendering, which would turn every 409 into a logged
  traceback. `problem.py` explains it.
- **Phase 5 shipped no module.** Web's `CorrelationIdMiddleware` installs with
  `app.add_middleware` unchanged; the one FastAPI-specific concern (a 500 skips the header stamp)
  is handled in `problem.py`, where the 500 is rendered.
- **Phase 6b binds `rn_forge.web.Authenticator`, not the commons verifier.** The commons `auth/`
  module still does not exist; the web protocol does, and it is what an application's verifier sits
  behind — so the binding is not a second protocol. Nothing here needs to change when commons lands.
- **Phase 6's timeout test was not written**: `run_checks` has no timeout, and adding one is a web
  decision (below).

**Web-plan changes this plan raised, executed in `rn-forge-web`** (the guiding principle's "raise it
against `rn-forge-web`"): `ProblemRegistry.rows()`, `ProblemRegistry.problem_for_status()` (the
folded `_status_mapping`), `build(..., problem=)`, and `errors_from_pointer_list` dropping the
leading `body` segment and rendering a missing field as `This field is required.` — without the last
one the `problem.validation-errors-are-rfc6901-pointers` case cannot pass on FastAPI. Tests added in
`rn-forge-web/tests/test_problem.py`; web's `wiring-fastapi.md` is now a pointer.

**Raised against the web plan:** a per-check timeout for `run_checks` (**resolved 2026-09-13**); the
generic `Page[T]` cannot be named literally `Page` in `components/schemas` (FastAPI emits
`Page_OrderOut_`) and the `operationId` convention covered CRUD only (**both resolved 2026-09-15**,
in `rn_forge/web/openapi.py` — see web plan §9.1; this package renames the component in
`install_problem_schema` and delegates `operation_id`).

**Open, and not this plan's to close alone:** Phase 8 — kiln has no `golden/python-web-api` yet
(kiln Phase E); and the `rn-forge-web` release tag.

## Alignment with the standardization plan (kiln revision 9)

Unlike the other four documents, this plan is written after `rn-forge/kiln` exists, so the alignment
is built in rather than bolted on. Stated once here, and assumed by every phase.

### 1. Where this package sits in the graph

```text
commons ──► cli ──► tooling ──► kiln / agentkit
   └──────────────────────────► web ──► django
                                 └───► fastapi          (this package)
   └──────────────────────────► azure
```

`rn-forge-fastapi` depends on **`rn-forge-web`**, which depends on **`rn-forge-commons`**. It imports
neither `rn_forge.cli` nor `rn_forge.tooling` — those are the command-line and file-owning layers
(kiln **D52**, ADR-0002), and a package that ships into an ASGI server has no business reaching
either. It also never imports `rn_forge.django`: django and fastapi are independent siblings at one
layer, not a chain.

### 2. The boundary is an import-linter contract

`.importlinter` gains `rn_forge.fastapi` in `root_packages`, and this contract alongside the two the
web plan's alignment §2 adds:

```ini
[importlinter:contract:fastapi-runtime-has-no-tooling]
name = rn_forge.fastapi never imports django, cli, tooling or Jinja
type = forbidden
source_modules =
    rn_forge.fastapi
forbidden_modules =
    rn_forge.django
    rn_forge.cli
    rn_forge.tooling
    jinja2
ignore_imports =
    rn_forge.fastapi.codegen -> *
    rn_forge.fastapi.codegen.* -> *
unmatched_ignore_imports_alerting = none
```

The `codegen` exemptions are written now, while the subpackage is empty — the same discipline
`rn_forge.django` already follows, and for the same reason: a fence added after the first module is a
fence that was never tested. `uv run lint-imports` gates every other CI job.

### 3. Releases are pinned git tags (kiln D46)

None of these packages is on PyPI; a release is a tag, and a `[tool.uv.sources]` workspace override
does not survive into a built wheel. Every rn-forge dependency is a pinned PEP 508 direct URL, and the
workspace override exists for local development only. The scaffold below is written that way, and the
installation guide documents the `git+…@tag` form rather than `uv add rn-forge-fastapi`.

Sequencing consequence: **`rn-forge-web` must have a release tag before this package can declare it.**
That is a harder edge than "web Phase 8 has landed".

### 4. Layout (kiln D55)

Six flat modules, all one kind of mechanism — FastAPI adapters over web primitives — so the package
stays flat, recorded as a decision rather than a default. If it grows past these phases, group by kind
of mechanism and keep public class names where they are. No compatibility re-exports, in any
direction, ever.

### 5. Code generation has a fixed home (kiln D37, D56)

Nothing in this plan generates code. When FastAPI scaffolds are wanted they ship as
**`rn-forge-fastapi[codegen]`**, live in `rn_forge.fastapi.codegen` and nowhere else, and register
under the entry-point group `rn_forge.kiln.generators`; kiln supplies only the Typer command surface.
kiln generates repo shape, a framework generates its own code (D56). The fence in §2 exists before the
first generator does. If a phase below starts rendering a template, it is in the wrong subpackage.

### 6. The acceptance is a golden repo

Under kiln **ADR-0005**, a claim not demonstrated in a runnable golden repo is not demonstrated —
the rule that caught standardization Phase C shipping ADR-0009 without evidence. So Phase 9 is not
documentation garnish: `golden/python-web-api` must wire this package end to end and pass
`uv sync && task validate` standalone. If that repo needs a hand-written adapter this package should
have supplied, the package is incomplete; if it needs more than a thin wiring module, the
web/fastapi split is wrong and the web plan's Phase 8.3 boundary test has failed.

### 7. Namespace collision — read before writing a single import

The import path is `rn_forge.fastapi` and the framework's is `fastapi`, one level apart. Same hazard
`rn-forge-azure` documents. Two mitigations, both cheap: always import the framework fully qualified
(`from fastapi import APIRouter`, never `import fastapi` inside this package), and add a test
asserting `rn_forge.fastapi.__path__` and `fastapi.__path__` are disjoint. The import-linter contract
in §2 is a third line of defence — it fails loudly if the package ever resolves to the framework.
Decide in Phase 0 whether the fallback name `rn_forge.fastapi_adapters` is needed, not after six
modules are written.

## Summary (read this first)

Everything here is thin — which was the argument for deferring the package, and is the reason it is
quick now. The value is not the line count; it is that six applications will not each invent their own
spelling of the same six adapters.

| Phase | Module | Prior art | Blocked on | Risk |
| --- | --- | --- | --- | --- |
| 0 | Scaffold, boundary contracts, namespace decision | — | web Phases 1–8 **released** | **blocking** |
| 1 | `problem.py` — `register_problem_handlers(app)` | intellibench `handlers.py` | web Phase 2 | low |
| 2 | `schemas.py` — pydantic mirrors of the web dataclasses | intellibench `models.py` | web Phases 2, 4 | low |
| 3 | `openapi.py` — inject `ProblemDetail` into the schema | intellibench `app.py::_custom_openapi` | Phases 1, 2 | **medium** |
| 4 | `dependencies.py` — cursor params, `Idempotency-Key`, `If-Match` | intellibench `pagination.py`, `idempotency.py`, `concurrency.py` | web Phases 3, 4, 5 | low |
| 5 | `middleware.py` — correlation wiring | intellibench `CorrelationIdMiddleware` | web Phases 1, 7 | low |
| 6 | `health.py` — `/healthz` + `/readyz` router factory | intellibench `routers/health.py` | web Phase 6 | low |
| 6b | `auth.py` — bearer/basic `Security` dependencies over the web contract | intellibench + cims auth layers | **commons `auth/`**, web Phase 10 | medium |
| 6c | `conformance.py` — drive the shared scenario table | — | web Phase 11, Phases 1–6b | low |
| 7 | Public API + docs, including `wiring-fastapi.md` promoted from prose | — | Phases 1–6 | none |
| 8 | The golden-repo acceptance (`golden/python-web-api`) | — | Phase 7, kiln Phase E | **the gate** |
| — | Deferred: `[codegen]` extra, SQLAlchemy stores, app factory | — | — | — |

Phases 1–6 are independent of each other once Phase 0 is done, except that 3 needs 1 and 2. Phase 8 is
the only phase that can fail the design rather than the code.

### Dependency policy for this package

The workspace principle applies in full: if a proven library does the job, depend on it and wrap it
thinly; do not reimplement it. Concretely, this package **depends on FastAPI** and contributes pykit's
syntax around it — it does not abstract FastAPI away. A consumer keeps `APIRouter`, `Depends`,
`Header` and `response_model` exactly as the framework documents them.

- **`fastapi`** is a hard dependency, not an extra. A package whose entire purpose is FastAPI adapters
  has nothing to install conditionally.
- **`pydantic`** arrives with FastAPI. Phase 2 mirrors the web package's dataclasses as pydantic
  models *here*, which is precisely the split the web plan chose: web ships dataclasses so a
  Django consumer carries no pydantic, and the FastAPI consumer gets the models from this package
  instead of writing them.
- **No `sqlalchemy`, no database driver, no `pydantic-settings`.** See "Things deliberately NOT in this
  package".
- Every dependency is justified in the `pyproject.toml` comment beside it and in the README's
  "Dependencies and why" section, including the negative results.

### Guiding principle for this plan

**Adapt, do not re-decide.** Every wire shape — the problem body, the cursor codec, the ETag
semantics, the idempotency reuse rule, the health-check aggregation — is settled in `rn-forge-web` and
is identical across both frameworks by construction. This package's only job is the FastAPI-shaped
plumbing: exception-handler registration, `Depends` factories, ASGI middleware wiring, router
factories and OpenAPI schema repair.

Two corollaries with teeth:

- **If a module here needs a decision, it belongs in the web plan.** A status code, a header name, a
  cursor encoding that is decided here is a divergence between the Django and FastAPI stacks by
  definition. Raise it against `rn-forge-web` instead.
- **If an adapter exceeds about forty lines, question it.** The extraction inventory put every
  candidate between five and forty lines. `openapi.py` (Phase 3) is the one place where more is
  expected, because it is working around FastAPI's schema collection rather than adapting a
  primitive.

### Conventions for this package

1. **Logging is injected, always** — the same rule `rn-forge-web` states, for the same reason. Nothing
   here imports `AppLogger` at module scope. Anything that logs takes a
   `log: Callable[[str, Mapping[str, Any]], None] | None = None` and stays silent when it is `None`.
2. **Metrics are optional hooks, never a hard dependency.**
3. **Errors derive from `AppException`** via `rn-forge-web`'s exception hierarchy. This package
   defines no new exception types — if it needs one, that is a web-plan change (see the guiding
   principle).
4. **Factories over module-level singletons**, exactly as the django plan requires: a router factory,
   a dependency factory, a handler-registration function. No module-level `app`, no module-level
   registry, nothing that needs monkeypatching to test.
5. **Curated `__init__.py`** following `rn_forge/commons/__init__.py`: every public symbol imported and
   listed in a sorted `__all__`.
6. **Async-first, because the framework is.** Handlers and dependencies are `async def`; anything
   taking a caller-supplied callable accepts sync or async and awaits what is awaitable — the rule
   `rn_forge.web.health` already follows.
7. **Strict typing, `py.typed`, module docstrings, explicit `__all__`,
   `from __future__ import annotations`.** Pyright strict covers this package automatically once it is
   under `packages/`. Note the one known friction: `from __future__ import annotations` plus pydantic
   models plus FastAPI's runtime introspection of annotations — verify in Phase 2 that the mirrors
   resolve, and record the outcome rather than discovering it in Phase 3.
8. **No application configuration surface.** A FastAPI app has its own `Settings` (usually
   `pydantic-settings`); this package takes configuration as function arguments and owns no settings
   facade. This is the same call `rn-forge-web` made, and the opposite of `rn-forge-django`, which has
   Django settings to hang one on.

### Things deliberately NOT in this package

- **`create_app` / an application factory.** The intellibench inventory is explicit that its shape —
  take a constructed `Settings` and a container, build nothing — is *a convention worth documenting,
  not code worth shipping*. Document it in the wiring guide and in the golden repo; do not ship a
  factory that every app will immediately need to escape.
- **Dependency injection / a container.** `ports_container.py` and `dependencies.py` in the surveyed
  app are application-specific. FastAPI's `Depends` is the DI framework; this package adds dependency
  *factories*, not a container.
- **Any store implementation.** `IdempotencyStore` is a protocol in `rn-forge-web`; its FastAPI-era
  implementations are SQLAlchemy- or Redis-backed and therefore belong to an application or to the
  deferred `rn-forge-sqlalchemy` package. Phase 4 ships the `Header` dependency that *reads* the key,
  and nothing that stores it.
- **SQLAlchemy anything** — models, sessions, repositories, the optimistic-`update` helper, the
  multi-tenant scoping hook. All recorded as deferred in the web plan under `rn-forge-sqlalchemy`, and
  all genuinely a separate package with a separate trigger.
- **Auth.** OIDC/JWKS verification is framework-agnostic and belongs in commons (the web plan's
  reasoning; the django plan's Phase 9 consumes it from there). A FastAPI `Security` dependency over it
  is a candidate for a later phase here, not for this plan — and it needs the commons module first.
- **A CLI surface.** ADR-0009's declared `[cli]` table belongs to `python-app` / `python-tool` repos.
  A `python-web-api` repo's entrypoint is `uvicorn`/`fastapi dev`, wired by kiln's `tasks/api.yml`.
- **Starlette-only support as a separate target.** The package depends on FastAPI. Where an adapter is
  genuinely Starlette-level (the correlation middleware is), say so in its docstring — but do not
  maintain two import paths for one middleware.

### Package scaffold and dependencies

`packages/rn-forge-fastapi/pyproject.toml`:

```toml
[project]
name = "rn-forge-fastapi"
version = "0.1.0"
description = "FastAPI adapters over rn-forge-web"
readme = "README.md"
authors = [{ name = "Rohit Narayanan", email = "rohit.nn@gmail.com" }]
requires-python = ">=3.14"          # workspace floor
dependencies = [
  # Pinned direct URLs, not bare names: these packages are not on PyPI and a release is a tag
  # (kiln D46). The `[tool.uv.sources]` override below is local development only.
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
  "rn-forge-web @ git+https://github.com/rn-forge/pykit@rn-forge-web-v0.1.0#subdirectory=packages/rn-forge-web",
  "fastapi>=0.121",                 # verify the floor against what actually resolves
]

[project.optional-dependencies]
testing = ["assertpy>=1.1", "httpx>=0.28", "pytest>=9.1.1"]
# codegen = ["rn-forge-tooling @ git+…", "jinja2>=3.1"]   # deferred (D37); the import fence exists now

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "rn_forge.fastapi"

[tool.uv.sources]                   # local development only — see alignment §3
rn-forge-commons = { workspace = true }
rn-forge-web = { workspace = true }
rn-forge-fastapi = { workspace = true }

[tool.pytest.ini_options]
addopts = "-ra --import-mode=importlib"
markers = ["unit: fast isolated tests"]
```

`rn-forge-commons` is declared directly even though `rn-forge-web` pulls it in: this package imports
`AppException` subclasses and commons facade symbols itself, and an implicit transitive dependency is
one refactor away from breaking.

**Pin floors against what actually resolves**, not against the numbers above — run `uv add --dry-run`
or check PyPI, and record the resolved version. `httpx` is in `testing` only, for FastAPI's
`TestClient` / `ASGITransport`.

Root `pyproject.toml`: add `"packages/rn-forge-fastapi"` to `[tool.uv.workspace] members`,
`rn-forge-fastapi = { workspace = true }` to `[tool.uv.sources]`, and `rn-forge-fastapi` to the
`workspace` dependency group. Pyright picks it up via `include = ["packages"]`. The dev group needs
`pytest-asyncio` with `asyncio_mode = "auto"` — the web plan adds it for the same reason.

Once kiln Phase F.1 has regenerated pykit's skeleton, also: add the package to
`[archetype.python-lib] packages` in `.rn-forge/kiln/config.toml` (it drives the generated per-package
CI matrix, build and release jobs), re-seed `.rn-forge/kiln/state.json` with `kiln apply` — `task lint`
fails with `has drifted from the committed state` until it agrees — and add the site to the root
`mkdocs.yml` nav and `docs/index.md`. Before that regeneration those files do not exist; do not create
them early.

### Validation command for every phase

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-fastapi
uv run ruff check packages/rn-forge-fastapi
uv run ruff format --check packages/rn-forge-fastapi
uv run pyright                       # strict; covers every package
uv run lint-imports                  # the boundary contracts — alignment §2
uv run --directory packages/rn-forge-fastapi --group docs mkdocs build --strict
```

After kiln Phase F.1, `task validate` runs all of the above and is what CI executes; the forms here
remain valid as its inner primitives.

---

## Phase 0 — Scaffold, boundaries, and the one thing that blocks everything

**This phase is blocking, and the scaffold is its easy half.**

### 0.1 — The prerequisite is a release, not a phase

Every module here imports `rn_forge.web`. Under kiln D46 that means `rn-forge-web` must have a **tag**
before this package's `pyproject.toml` can declare it — the workspace override makes local development
work regardless, which is exactly the trap: the package will build locally and be unresolvable for
anyone outside the workspace. Confirm `rn-forge-web-v0.1.0` (or later) exists before writing the
dependency line, and pin the tag that exists rather than the one you expect.

Web Phases 1–8 must all have landed, not just the ones a given module names: Phase 8's curated
`__init__` is what every import here goes through.

### 0.2 — The namespace decision

Resolve the `rn_forge.fastapi` / `fastapi` collision now (alignment §7), not after six modules. The
default is to keep `rn_forge.fastapi`, import the framework fully qualified everywhere, and add the
disjoint-`__path__` test. Record the decision and its reason in the package README. The fallback
`rn_forge.fastapi_adapters` is available and costs nothing today; it costs a breaking rename later.

### 0.3 — Scaffold

Standard workspace-member layout, copied from `rn-forge-cli`:

```
packages/rn-forge-fastapi/
  pyproject.toml
  README.md
  mkdocs.yml
  docs/{index.md,guides/,api/}
  src/rn_forge/fastapi/{__init__.py,py.typed}
  tests/__init__.py
```

`mkdocs.yml` copies commons' verbatim except `site_name`/`site_description`.

Add the contract from alignment §2 to `.importlinter` and `rn_forge.fastapi` to its `root_packages`,
including the `codegen` exemptions while the subpackage is empty.

**Phase 0 exit criteria:** `rn-forge-web` has a release tag and it is the one pinned;
`uv sync --all-extras` resolves; `import rn_forge.fastapi` works; `uv run pyright` clean;
`uv run lint-imports` green with the new contract present; the namespace decision recorded in the
README with its reason.

---

## Phase 1 — `problem.py`: exception handlers

The single highest-value adapter in the package, and the reason an app that skips it ends up with two
error formats.

`register_problem_handlers(app, *, registry=None, log=None) -> None` registers three handlers on a
`FastAPI` (or bare Starlette) application, each producing an `application/problem+json` body built by
`rn_forge.web.problem`:

1. **The registry's own exceptions** — everything `rn_forge.web`'s registry knows, mapped to its slug
   and status.
2. **`StarletteHTTPException`** — for an `HTTPException` carrying no registered exception type, map
   the status code to a slug through the default table. The intellibench inventory records this as
   `_status_mapping`; **it folds into the web package's default registry**, not into a table here —
   per the guiding principle, a status-to-slug decision is a wire decision and must be identical for
   Django. If `rn_forge.web` does not expose it, that is a web-plan change, not a local table.
3. **`RequestValidationError`** — FastAPI's 422 body is its own shape; normalize it through
   `rn_forge.web.problem`'s validation-error normalizer (web §2.3) so a client sees one error format
   for a bad body and a bad state alike.
4. **Bare `Exception`** — a 500 whose body carries no detail and whose *log* carries everything. The
   `log` parameter is how the detail escapes; there is no fallback logger (Convention 1).

Correlation: every problem body carries the current correlation ID from `rn_forge.web.context`, which
Phase 5's middleware has already set. Test that a handler firing with no middleware installed still
produces a valid body — a library that requires a specific middleware order and does not say so is a
support burden.

**Tests:** one registered exception, one bare `HTTPException(404)`, one `RequestValidationError` from a
real request body, one unhandled `ZeroDivisionError`; each asserted on status, `content-type`, body
shape and the correlation field. Assert the 500 body leaks nothing and the injected `log` received it.

**Do not** register these handlers automatically on import, and do not ship an `app` that has them.

---

## Phase 2 — `schemas.py`: pydantic mirrors

`rn-forge-web` ships its wire shapes as dataclasses, deliberately, so a Django consumer carries no
pydantic (web plan, guiding principle). FastAPI consumers need `BaseModel`s to use them as
`response_model`s — and the mirroring is the job this package exists to do once instead of six times.

Ship pydantic mirrors of every public web wire shape: `ProblemDetail`, `Page[T]` and its page
metadata, and whatever else web Phase 8 exports as a wire shape. Each mirror:

- carries the **same field names and JSON shape** as its dataclass — a test asserts that
  `Mirror.model_validate(asdict(dataclass_instance))` round-trips, so a divergence fails loudly
  instead of showing up in a generated client;
- is generic where the dataclass is (`Page[T]`), so `Page[UserOut]` works as a `response_model`;
- converts both ways: `from_wire(dataclass) -> Mirror` and `to_wire() -> dataclass`.

### 2.1 — The camelCase rule is enforced here, in code

`api-conventions.md` (web Phase 9.1) fixes the wire as **camelCase, with `snake_case` in Python** —
the Google JSON Style Guide / Microsoft REST Guidelines / proto3-JSON convention, and what a
generated TypeScript client and every mainstream UI HTTP layer expect. This package is where that
becomes true for FastAPI, and it must be machinery rather than per-model discipline:

```python
class WireModel(BaseModel):
    """Base for every schema crossing the wire: camelCase out, either in."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,      # accept snake_case on input too
        from_attributes=True,
    )
```

Every mirror in this module derives from `WireModel`, and it is exported so an application's own
schemas derive from it too — that is the difference between a rule that holds and a rule that holds
until someone adds a model in a hurry.

Three details that decide whether this actually works:

- **Responses must serialize by alias.** FastAPI serializes a `response_model` using the field names
  unless told otherwise; set `response_model_by_alias=True` (it is the default for `response_model`,
  but assert it in a test rather than trusting it across versions) and document it in the wiring
  guide for hand-built `JSONResponse`s, which do not go through the model at all.
- **Input accepts both spellings.** `populate_by_name=True` means an internal caller can post
  `snake_case` without a client change. Accepting both on input and emitting one on output is the
  forgiving direction.
- **RFC 9457's core members are exempt** — `type`, `title`, `status`, `detail`, `instance` are single
  lowercase words and `to_camel` leaves them alone. Verify this with a test rather than reasoning
  about it, because a future alias generator change would silently rename the error contract.

Query and path parameter names follow the same rule (`pageSize`, `pageToken`) — see Phase 4.

**Verify Convention 7's known friction here**, before Phase 3 depends on it: `from __future__ import
annotations` plus pydantic generics plus FastAPI's runtime annotation introspection. If the combination
misbehaves, the fix is local to this module (drop the future import in this file, with a comment saying
why) — record the outcome either way.

---

## Phase 3 — `openapi.py`: put the error type back in the schema

**The non-obvious phase, and the one worth the most to a client generator.** FastAPI builds
`components/schemas` from the `response_model`s routes declare. The problem handlers in Phase 1 build
error bodies by hand, so the schema collection never sees `ProblemDetail` — and a generated TypeScript
client ends up with no error type at all. The surveyed app patched `app.openapi` to inject it; that
patch is the prior art.

### 3.1 — Three conventions before the code

The generated client is the interface a UI actually consumes, so these are wire decisions in the
sense the guiding principle means, and all three are settled in `api-conventions.md` rather than
here. This package implements them:

- **OpenAPI 3.1.0.** FastAPI emits 3.1 on current versions; pin it explicitly and assert the emitted
  `openapi` version in a test. The Django side pins drf-spectacular's `OAS_VERSION` to match. A
  3.0-vs-3.1 mismatch changes nullability and the JSON Schema dialect, which changes generated types.
- **Identical component names.** `ProblemDetail`, `Page`, `CheckResult`, `HealthReport` appear under
  exactly those names in `components/schemas` on both stacks. FastAPI derives component names from
  the model class name, so the Phase 2 mirrors must be named for the wire, not for this package.
- **One `operationId` convention.** This is the one most easily missed and the most visible: a
  generator turns `operationId` into the client's method name, so two stacks that differ here produce
  different call sites for the same endpoint even when every byte of JSON agrees. FastAPI's default
  mangles the function name, path and method together; override it with a
  `generate_unique_id_function` implementing the convention `api-conventions.md` names, and ship that
  function from this module so an application sets it once on `FastAPI(...)`.

### 3.2 — The schema repair

Ship `install_problem_schema(app, *, default_responses=True) -> None`:

- injects the Phase 2 `ProblemDetail` mirror into `components/schemas`, idempotently, surviving
  FastAPI's own schema caching;
- when `default_responses` is on, adds `application/problem+json` responses for the status codes the
  registry actually uses to every route that does not declare its own — so the generated client knows
  a 409 or a 412 is possible;
- leaves a route's explicit `responses=` untouched. Never overwrite what an author declared.

This is the one module where more than forty lines is expected, because it is working around schema
collection rather than adapting a primitive. Keep the workaround in *this* module and out of Phase 1 —
handler code that also edits a schema is two concerns in one function.

**Tests:** build a small app with one route, call `app.openapi()` twice (caching), assert
`ProblemDetail` is present exactly once, assert a declared `responses=` survives, and snapshot the
generated schema for one route so a FastAPI upgrade that changes schema collection fails here rather
than in a consumer's client build.

---

## Phase 4 — `dependencies.py`: the three header/query dependencies

Five to ten lines each; the value is that all six applications spell them the same way.

- **`page_params(*, cap: int, default: int)`** — a dependency factory returning
  `(page_token, page_size)` from the query parameters **`pageToken`** and **`pageSize`**, with the
  size clamped through `rn_forge.web.pagination.clamp_page_size`. The names are AIP-158's as fixed in
  web §4.1, not this package's choice. **Clamped, never rejected** — that is the wire contract web
  Phase 4 settled, it is AIP-158's own rule, and a FastAPI `Query(le=...)` would violate it by
  returning 422. **Do not use `le=`** — state the cap in the parameter description so the schema
  documents it without enforcing it as validation.
- **`require_idempotency_key()`** — a `Header(...)` dependency returning the key and raising the
  `rn_forge.web` idempotency exception when it is missing or malformed, so Phase 1's handler renders
  it. It reads the key; it does not store it (see "Things deliberately NOT in this package").
- **`require_if_match()`** — a `Header(...)` dependency returning the parsed `If-Match` validators via
  `rn_forge.web.concurrency`, raising the 428 exception when absent on an unsafe method. The 412-vs-409
  and validator-format questions are settled in web §3.1/§3.2; do not re-decide them here.

Each is a **factory** (Convention 4), so `cap` and header names are per-app arguments rather than
module constants.

**Tests:** a route per dependency exercised through `TestClient`, asserting the clamped limit, the
problem body for each missing/malformed header, and that a valid header passes through unchanged.

---

## Phase 5 — `middleware.py`: correlation wiring

**Expect this phase to be nearly empty, and say so honestly if it is.** Web Phase 7 ships a **pure-ASGI**
correlation middleware (over `asgi-correlation-id` if Phase 0.2 of that plan confirmed it). A pure-ASGI
middleware installs on FastAPI with `app.add_middleware(...)` and nothing else — so the FastAPI-specific
content of this phase may be one re-export and a paragraph in the wiring guide.

What this phase does own:

- a single `add_correlation_middleware(app, *, header_name=..., ...)` convenience so the wiring guide
  has one call to show and the golden repo has one line, rather than every app importing the ASGI class
  and passing its own arguments;
- **the ordering rule**, tested: the correlation middleware must run before anything that logs or
  builds a problem body, and the test is a request that raises, asserting the correlation ID appears in
  both the problem body and the injected log record;
- a documented answer for apps fronted by infrastructure that stamps a different header.

If it turns out there is nothing to wrap — the web middleware installs cleanly with no FastAPI-specific
adaptation at all — **do not ship a module for the sake of symmetry.** Fold the convenience into
`__init__.py` if it is one function, or drop it and document `app.add_middleware(...)` directly. A
one-line wrapper that exists to make a table row is cost without benefit.

---

## Phase 6 — `health.py`: the router factory

`health_router(*, checks, prefix="", log=None) -> APIRouter` over `rn_forge.web.health`:

- **`/healthz`** — liveness. Returns 200 as long as the process is serving. It runs no checks; a
  liveness probe that runs a database query restarts a healthy pod when the database blips.
- **`/readyz`** — readiness. Runs the registered checks through `rn_forge.web.health.run_checks`
  (async, so no `run_checks_sync` here — that form is the django plan's), returning 200 with the
  per-check report, or **503** with the same report when any required check fails. The semantics are
  web Phase 6's; this is plumbing.

A factory, not a module-level router (Convention 4): two apps in one process, and tests that need no
monkeypatching.

**Tests:** all checks pass → 200; one required check fails → 503 with the failing check named; an
optional check fails → 200 with the check reported as degraded; a check that raises is reported as a
failure rather than propagating; a check that takes too long is reported rather than hanging the probe.
Sync and async check callables both work.

---

## Phase 6b — `auth.py`: the authentication binding

**Un-deferred.** The first draft deferred auth entirely, blocked on a commons OIDC module that did not
exist. Two things changed: web Phase 10 now specifies the contract (`Principal`, the protocols, the
401/403 boundary and the RFC 6750 `WWW-Authenticate` construction), and the commons plan's §A.2 now
carries the verification module as a named blocker rather than an aspiration. What is left here is a
binding, and it is small.

**Still blocked on** the commons `auth/` module and web Phase 10. Do not start it earlier; a binding
written against a protocol that does not exist yet is a second protocol.

Ship:

- **`bearer_auth(*, verifier, authorizer=None) -> Security dependency`** — reads the token per
  RFC 6750, calls the commons verifier, maps verified claims to a `rn_forge.web.auth.Principal`, and
  returns it. The claims→`Principal` mapping is web's (§10.2), not this package's.
- **`basic_auth(*, verifier, realm=...)`** — RFC 7617, for local development and simple internal
  deployments. It produces the *same* `Principal` and the *same* 401 challenge as the bearer path.
  Document the intended use plainly in the docstring; a convenience mechanism that reads as a
  production one is how a bypass ships.
- **`requires(...)`** — a dependency factory over `web.auth.Requirement`, so scope and role checks are
  declarative and evaluate identically to Django's.

**Do not use FastAPI's `HTTPBearer`/`HTTPBasic` defaults unexamined.** Their 401 bodies are FastAPI's
own shape and their challenge headers are not RFC 6750's `error=`/`error_description=` form. Raise the
`rn_forge.web` exceptions and let Phase 1's handlers render them, so the body is `problem+json` like
every other error. This is the specific thing that would otherwise leave a UI with two error formats.

**Tests:** valid bearer → `Principal` with the expected scopes; missing credentials → 401 whose
`WWW-Authenticate` matches RFC 6750 §3 and whose body is `problem+json`; invalid token → 401 with no
verification reason in the body but the reason present in the injected `log`; valid token, wrong
scope → **403 with no challenge header**; basic auth produces the same `Principal` shape.

---

## Phase 6c — `conformance.py`: the driver

Fifteen lines, and the only test in this package that can fail because of something `rn-forge-django`
does.

`rn_forge.web.conformance.CASES` (web Phase 11) is a framework-free table of request/response
scenarios. This phase builds a minimal FastAPI application wired with everything Phases 1–6b ship,
runs every case through `TestClient`, redacts with `web.conformance.redact`, and asserts equality
against the table.

- **It asserts against the table, never against Django's output.** Two stacks agreeing on the wrong
  thing is not conformance.
- **It lives in `tests/`, not in `src/`** — unlike the table itself, the driver is a test.
- **A case this package cannot satisfy is a finding, not a skip.** Either the adapter is missing (add
  it here) or the case encodes a decision FastAPI cannot honour (raise it against the web plan). A
  `pytest.skip` in this file silently removes the guarantee the whole exercise exists for.

The equivalent driver in `rn-forge-django` is a named amendment in the web plan's §A.1; both must
exist for either to mean anything.

---

## Phase 7 — Public API and docs

1. `src/rn_forge/fastapi/__init__.py` imports and re-exports every public symbol, `__all__` sorted,
   matching `rn_forge/commons/__init__.py`'s style.
2. `docs/index.md`, `docs/guides/{installation,quickstart}.md`, `docs/api/*.md` (one page per module)
   and the `mkdocs.yml` nav. `mkdocs build --strict` fails on a nav entry with no file, so add each
   page in the same commit as its module.
3. **`wiring-fastapi.md` is promoted, not rewritten.** The web plan's Phase 9.2 guide was written to be
   promotable into code; this package is that code. The guide moves here, shrinks to the wiring that is
   left, and the web plan's copy becomes a pointer. If it does not shrink substantially, this package
   did not adapt what it claimed to.
4. **Installation guide documents the `git+…@tag` form** per kiln D46, never `uv add
   rn-forge-fastapi`. The equivalent omission in tooling's guide was a review finding (commons plan
   D.7).
5. A **"Dependencies and why"** README section, including the negative results — what was deliberately
   not wrapped, and the app-factory decision.
6. Add the site to the root `mkdocs.yml` nav and `docs/index.md`.

---

## Phase 8 — The golden-repo acceptance

**This is the gate, and it can fail the design rather than the code.**

`golden/python-web-api` (kiln Phase E, `framework = fastapi`) must wire this package end to end:
problem handlers, the OpenAPI injection, at least one paginated route using the cursor dependency, the
correlation middleware, and the health router. Acceptance, run in that repo standalone:

```bash
cd ../kiln/tests/fixtures/golden/python-web-api
uv sync && task validate
uv run --group docs mkdocs build --strict
```

Three things the golden repo has to demonstrate, each of which is a claim this plan is making:

1. **The wiring module is thin.** If it exceeds roughly a page, the web/fastapi split is wrong and the
   web plan's Phase 8.3 boundary test has failed — report that rather than padding the repo.
2. **No hand-written adapter.** If the repo needs an adapter this package should have supplied, the
   package is incomplete; add the phase rather than the file.
3. **The generated OpenAPI has an error type.** Generate a client (or assert on the schema) and check
   `ProblemDetail` is reachable — that is Phase 3's whole justification and it is invisible without
   this check.

Under kiln ADR-0005 the golden repo is authored and reviewed *before* intellibuild copies it, and a
template change never made in a golden repo is a bug. Do not skip to the application.

---

## Deferred — do not build these yet

- **`rn-forge-fastapi[codegen]`.** Router/schema/dependency scaffolds under `rn_forge.fastapi.codegen`,
  registered in `rn_forge.kiln.generators` (kiln D37, D56). The import fence exists from Phase 0; the
  generators wait for D2 to be lifted, the same as Django's.
- **`rn-forge-sqlalchemy` — parked (2026-09-13).** The declarative base, naming convention, `TimestampMixin`, the optimistic
  `update`/`StaleVersionError` repository helper, and a SQLAlchemy `IdempotencyStore`. Recorded in the
  web plan with its own trigger: the first SQLAlchemy application rewritten on this kit. intellibuild
  is that application, so this is the **next** package to plan after this one — plan it with
  intellibuild's spec, not ahead of it.
- **Multi-tenant row scoping.** The `before_execute` isolation hook and RLS binding. The web plan's
  reasoning stands: generalizing a tenancy model from one application's assumptions produces a shape
  nobody else can use. Revisit when a second app's rewritten spec states its tenancy requirements.
- ~~**A FastAPI `Security` dependency over OIDC/JWKS.**~~ **No longer deferred — shipped as Phase
  6b.** Both things it waited on — web Phase 10's contract and the commons verification module —
  have landed.
- **Server-sent events / websockets / background tasks.** No prior art in the survey, no second
  consumer, no evidence of a shared shape. Not deferred with a trigger — simply out of scope.

---

## Final checklist before calling this done

- [ ] `rn-forge-web` has a release tag and this package pins it as a direct URL; the workspace override
      is local development only (kiln D46) — **the pin is written; the tag is not cut** (web plan
      step 12, needs a decision to push)
- [x] `uv sync --all-extras && uv run pytest packages/rn-forge-fastapi` green
- [x] `uv run pyright` clean across every package
- [x] `uv run ruff check` and `ruff format --check` clean over the changed packages
- [x] `uv run lint-imports` green with `fastapi-runtime-has-no-tooling` present, including the
      `codegen` exemptions written while the subpackage is empty
- [x] `rn_forge.fastapi` imports neither `rn_forge.django`, `rn_forge.cli` nor `rn_forge.tooling`
- [x] The namespace decision recorded, and the `__path__`-disjoint test passes
- [x] No wire decision was made in this package — every status code, header name and encoding traces to
      `rn-forge-web`; anything that could not, was raised against the web plan (see
      "Implementation status")
- [x] `WireModel` ships and every mirror derives from it; responses serialize by alias; RFC 9457's
      core members survive the alias generator unchanged (asserted, not assumed)
- [x] Pagination parameters are `pageSize`/`pageToken`, the size is clamped rather than rejected, and
      no `le=` bound appears on the page-size query parameter
- [x] The emitted schema is OpenAPI **3.1.0**; the shared non-generic components are named exactly
      `ProblemDetail`, `CheckResult`, `HealthReport`; the paginated envelope is `Page<Item>`
      (`install_problem_schema` renames pydantic's `Page_OrderOut_`); the `operationId` convention is
      applied through a shipped `generate_unique_id_function` that calls `rn_forge.web.openapi`
- [x] Phase 6b's 401 carries an RFC 6750 §3 `WWW-Authenticate`, its 403 carries none, and neither
      body leaks a verification reason
- [x] Phase 6c's conformance driver runs every case in `rn_forge.web.conformance.CASES` with no
      skips, and asserts against the table rather than against Django's output
- [x] Phase 2's mirrors round-trip against the web dataclasses, asserted by a test
- [x] Phase 3's schema injection is idempotent, survives caching, and never overwrites a declared
      `responses=`
- [x] Phase 5 shipped a module only if there was something to wrap — no one-line wrapper for symmetry
- [x] `src/rn_forge/fastapi/__init__.py` re-exports every public symbol, `__all__` sorted
- [x] `uv run --directory packages/rn-forge-fastapi --group docs mkdocs build --strict` clean
- [x] `wiring-fastapi.md` promoted from the web plan and visibly shorter than it was
- [ ] `golden/python-web-api` wires the package end to end and passes `task validate` standalone; its
      wiring module is about a page; its generated OpenAPI contains `ProblemDetail` — **blocked:
      kiln Phase E has not created the golden repo**
- [x] The package is wired into pykit's repo shape (workspace members, sources, workspace dependency
      group, CI job, root `mkdocs.yml` nav and `docs/index.md`). `[archetype.python-lib] packages`
      and the `state.json` re-seed wait for kiln Phase F.1, as for web
- [x] `CLAUDE.md` and the root README describe the package and the dependency direction
      (`fastapi → web → commons`, siblings with `django`)
- [x] Nothing committed or pushed — leave the working tree for review

## Not in this plan (deliberately deferred)

- **Any change to intellibench or intellibuild.** intellibuild is rebuilt by `kiln new` against these
  libraries (standardization plan Phase F.4); what this plan owes it is the package and the golden
  repo, not patches.
- **The `rn-forge-web` modules themselves.** Every gap found while writing an adapter here is a web-plan
  change, executed there. Record it; do not work around it locally.
- **Lowering any package's Python floor.** `>=3.14` across the workspace; a change is a workspace
  decision with its own gate.
