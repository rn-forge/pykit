# `rn-forge-web` — new package plan

Scope: a **new** workspace package, `packages/rn-forge-web` (import path `rn_forge.web`), holding the
HTTP/API primitives that are genuinely framework-agnostic — shared by Django/DRF, FastAPI/Starlette,
and anything else that speaks HTTP. It depends on `rn-forge-commons` and on whatever small set of
proven libraries earns its place (see "Dependency policy" below).

This package exists because the same seven concerns were implemented **twice, independently**, by two
codebases that never shared code, and the two implementations disagree in instructive ways. That is
strong evidence the concerns are real, and it is why this package — not a framework package — is
where they belong.

Three sources feed this plan, and it is self-contained:

- The `cims-backend` survey (`/Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend`,
  performed 2026-07-22) — Django 5.2 + DRF, sync, `structlog`.
- A survey of `intellibench` (`/Users/rohitnarayanan/Devel/workspaces/walgreens/intellibench`,
  performed 2026-08-31) — FastAPI + SQLAlchemy/Alembic on Postgres, **fully async**, `structlog`,
  `pydantic`. Read `apps/api/src/intellibuild_api/*`, `libs/backend/ports/src/intellibuild_ports/*`,
  `libs/backend/adapters/src/intellibuild_adapters/{storage,devops/azure,llm,secrets}/*`,
  `libs/backend/config/src/intellibuild_config/doctor.py`.
- The existing pykit workspace as it stands on 2026-08-31 (`packages/rn-forge-commons`,
  `packages/rn-forge-django`), for conventions and the package-scaffold shape.

### How to read the two surveyed applications

**Both cims and intellibench are work-in-progress and treated as throwaway.** Their specifications are
being rewritten now, and both will be **reimplemented** afterwards — against these libraries. So:

- Their code is **prior art**, not a compatibility constraint. Nothing here is shaped to keep an
  existing call site working; where a survey found a bug or a weaker design, this plan fixes it
  outright rather than parameterizing around it.
- Their **runtime pins do not constrain this package.** cims's 3.12 and intellibench's 3.13 floors
  belong to code that is being deleted; the rewrites adopt the interpreter pykit targets. The Python
  floor stays `>=3.14` — see Phase 0.
- The **deliverable is bigger than the code**: the reimplementations must not re-derive these
  primitives or invent their own spellings for them. Phase 9 ships the context pack that app
  specifications are written against, and it is as load-bearing as any module here.

Two companion documents: [`azure-library-plan.md`](./azure-library-plan.md) (the adapter package) and
[`django-upgrade-plan.md`](./django-upgrade-plan.md) (which this plan **amends** — see "Amendments to
plans already written" below; those amendments have been applied, and five django phases are now
blocked on phases here). **Start from [`README.md`](./README.md)** — it carries the execution order
across all five plans and the list of decisions that must be made before implementation begins.

## Alignment with the standardization plan (kiln revision 9)

**Written 2026-09-10.** This plan was drafted before `rn-forge/kiln` existed. Nothing in its module
design changed — the seven concerns, the two-implementation evidence and every disagreement resolved
below stand. What changed is the **workspace around it**: the library graph, the release contract,
the package layout rule, and who the consumers are. Read this section before Phase 0; the rest of the
document is unchanged except where it is corrected in place and marked.

Authority: the kiln standardization plan (revision 9, since retired; D-numbers resolve through
`../../../kiln/docs/plans/context.md` §2.2) and
`../../../kiln/docs/adr/` — chiefly ADR-0002 (the dependency graphs), ADR-0005 (archetypes and golden
repos) and D46 (releases are pinned git tags).

### 1. Three library layers, and `rn-forge-web` is on the runtime side of all of them

The development layer split in two (kiln **D52**). The graph is now:

```text
commons ──► cli ──► tooling ──► kiln / agentkit
   └──────────────────────────► web ──► django
   └──────────────────────────► web ──► fastapi
   └──────────────────────────► azure
```

`rn-forge-web` depends on **`rn-forge-commons` and nothing else in the workspace**. It must never
import `rn_forge.cli` or `rn_forge.tooling`: those are the command-line and file-owning layers, and a
package that ships into an ASGI server has no business reaching either. This is the same rule that
already keeps a web framework out of commons, applied one level up.

### 2. The boundary check is an import-linter contract, not a grep

`.importlinter` at the repo root is the executable statement of the graph, and `uv run lint-imports`
gates every other CI job (CLAUDE.md → "The import boundary is executable"). **Phase 0.3 adds two
contracts rather than the `grep` this plan originally specified** — a grep misses transitive imports,
which is exactly how a boundary rots:

```ini
[importlinter:contract:web-is-framework-free]
name = rn_forge.web never imports a web framework, cli or tooling
type = forbidden
source_modules =
    rn_forge.web
forbidden_modules =
    django
    fastapi
    starlette
    rest_framework
    rn_forge.cli
    rn_forge.tooling

[importlinter:contract:web-layers]
name = django and fastapi depend on web, web depends on commons, never the other way round
type = layers
layers =
    rn_forge.django : rn_forge.fastapi
    rn_forge.web
    rn_forge.commons
```

`rn_forge.web` joins `root_packages`. The `:` in the layers contract makes django and fastapi
*independent siblings* at one layer — neither may import the other. Keep the grep in the phase
validation block as a fast local check; the contract is what CI trusts.

### 3. Releases are pinned git tags, not PyPI versions (D46)

The scaffold in "Package scaffold and dependencies" below declares `dependencies = ["rn-forge-commons"]`
with a `[tool.uv.sources]` workspace override. **That is not what a consumer resolves.** None of these
packages is published to PyPI; a release is a tag, and a source override does not survive into a built
wheel. The corrected form, matching `packages/rn-forge-cli/pyproject.toml` as it ships today:

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
  "rfc9457>=0.4.1",                 # phase 2 — if Phase 0 confirms the fit
]

[tool.uv.sources]
rn-forge-commons = { workspace = true }   # local development only; see kiln D46
rn-forge-web = { workspace = true }
```

Pin the commons tag that exists when the package is scaffolded, not a placeholder. The package's own
first release is `rn-forge-web-v0.1.0`, and its installation guide documents the `git+…@tag` form —
never `uv add rn-forge-web`. That guide is a Phase 8 deliverable, not an afterthought: the equivalent
sentence in tooling's guide was a review finding (commons plan D.7).

### 4. Package layout: flat is a decision now, not a default (D55)

Commons, cli and tooling were re-laid-out into sub-packages by kind of mechanism because 23 flat
modules stopped answering "where does this go". `rn-forge-web` ships **seven modules that are all one
kind of mechanism** — inbound HTTP wire semantics — so it stays flat, and that is recorded as a
decision rather than an accident. The D55 rule that binds this package: group when the tree stops
being readable, keep public class names stable when you do, and never leave a compatibility re-export
behind. The curated `__init__.py` (Convention 4) is what makes a later regrouping cheap.

### 5. The consumers are archetypes, and a claim needs a golden repo

Both rewrites this plan is written for now have names in kiln's archetype catalogue (**D53**):

| Rewrite | Archetype | kiln golden repo | Phase |
| --- | --- | --- | --- |
| intellibuild (successor to intellibench) | `python-web-api`, `framework = fastapi` | `golden/python-web-api` | kiln Phase E, then F.4 |
| the cims successor | `python-web-app`, `framework = django`, `frontend = angular` | `golden/python-web-app-django` | kiln Phase E |

This changes Phase 9 from a documentation deliverable into a **testable** one. Under kiln **ADR-0005**
a claim not demonstrated in a runnable golden repo is not demonstrated — the same rule that caught
Phase C shipping ADR-0009 without evidence. So:

- `docs/adoption/wiring-fastapi.md` and `wiring-django.md` (Phase 8.3 / Phase 9.2) are the prose form;
  the **runnable** form is the corresponding golden repo, which `uv sync && task validate` proves.
- Phase 9.4's "worked minimal example per framework, exercised by a test" is satisfied by the golden
  repo when it lands. Until kiln Phase E exists, keep the in-repo examples — they are the interim, and
  they are what the golden repo is authored from.
- Phase 8.3's own test of the boundary stands and gets sharper: if either wiring guide runs past a
  page, or either golden repo needs more than a thin adapter layer, the split is wrong.

### 6. Adding a package to pykit is a repo-shape change

pykit is the `python-lib` archetype (kiln D53): a uv workspace of published library packages, with a
per-package CI matrix and per-package release tags. After kiln Phase F.1 regenerates pykit's skeleton,
adding `packages/rn-forge-web` is not just a `pyproject.toml` edit. The full list, in order:

1. Root `pyproject.toml`: `[tool.uv.workspace] members`, `[tool.uv.sources]`, the `workspace`
   dependency group.
2. `.rn-forge/kiln/config.toml` → `[archetype.python-lib] packages` — this is what drives the
   generated CI matrix, the build and the release job.
3. `scripts/standards/check_rn_forge_deps.py`'s `REQUIRED`/`ALLOWED` config header, if the new package
   changes what this repo is allowed to depend on.
4. Re-seed `.rn-forge/kiln/state.json` (`kiln apply`); `task lint` fails with
   `has drifted from the committed state` until it agrees.
5. `.importlinter` — §2 above.
6. Root `mkdocs.yml` nav (`!include packages/rn-forge-web/mkdocs.yml`) and `docs/index.md`.

Before that regeneration, items 2–4 do not exist and items 1, 5, 6 are the whole list. Do not invent
kiln files early.

### 7. Validation commands

Every phase's validation block gains `uv run lint-imports`. After kiln Phase F.1 the repo's public
verbs are the ten kiln wrappers (ADR-0008) — `task validate` runs lint, typecheck, test and the strict
docs build — and the raw `uv run …` forms in this document become the inner primitives. Both work;
prefer `task validate` once it exists, because that is what CI runs.

### 8. What did not change

The module designs, every resolved disagreement (§2.5, §3.1, §3.2, §5.1), the "Things deliberately NOT
in this package" list, the dependency-policy rules, and Conventions 1–6. The `rn-forge-fastapi`
deferral **did** change — its trigger has fired; see
[`fastapi-library-plan.md`](./fastapi-library-plan.md) and the "Deferred" section below.

## Implementation status — applied 2026-09-11

**This plan is executed.** `packages/rn-forge-web` exists in the working tree with all eleven phases
applied; the final checklist at the bottom is ticked with the evidence. Two things a reader of the
plan alone would get wrong, so they are recorded here rather than only in the package:

**Phase 0.2 decided both candidate libraries — both rejected.**

- **`asgi-correlation-id` 5.0.1: rejected on criterion 5.** It declares `starlette>=0.18` as a hard
  runtime dependency, not an extra, so adopting it would make every Django/WSGI consumer install
  Starlette to read a ContextVar. Criteria 1–3 pass; criterion 5 is disqualifying on its own.
  Phases 1 and 7 are therefore built as originally specified, and `asgi.py` declares its six ASGI
  type aliases locally. **The `asgi` extra in the scaffold above does not exist** — the package has
  no optional dependencies at all.
- **`rfc9457` 0.4.1: rejected on criterion 2.** No framework dependency (only `multidict`) and it
  ships `py.typed`, but its `Problem` is an `Exception` with its own `__init__`, `__str__` and
  `__repr__`, which cannot compose with `AppException` without one contract losing. It also models
  no `instance` member and has no parse direction, so the wrapper would be larger than the
  implementation. §2.1 is built as written.

So `rn-forge-web` has **exactly one dependency, `rn-forge-commons`**, and the negative results for
Phases 3–6 are recorded in the package README with their date.

**Four things the implementation settled that this plan left open or got slightly wrong:**

1. **`str(exc)` was the wrong source for a sub-500 `detail`.** `AppException.__str__` renders
   `"<error_code> | <message> | <error_data>"`, so §2.2 as specified would have put the exception's
   whole context dictionary on the wire. `build()` reads `.message` instead. A test caught it.
2. **`HealthReport` needed an `as_body()`.** Its `http_status` field is both snake_case — violating
   the casing rule of Phase 9 — and a restatement of the status line. `as_body()` emits `status` and
   `checks` only; `http_status` stays on the dataclass for the framework layer to read.
3. **`InMemoryIdempotencyStore` cannot implement both protocols.** One class cannot carry a `def`
   and an `async def` under the same name, and renaming the async one would make it satisfy neither
   protocol. Two classes ship, the async one delegating to the sync one so they cannot drift.
4. **A conformance case can depend on another, and that had to become data.** The idempotency replay
   case only replays something. `ConformanceCase.depends_on` names its prerequisites explicitly, and
   each case starts from a fresh application — otherwise a driver under a randomizing test runner
   passes or fails by luck. `case_by_id` resolves them.

**The conformance table is proven in-package, which the plan did not anticipate.** Phase 9.4's
"worked minimal example per framework, exercised by a test" is delivered as three examples under
`docs/adoption/examples/`, and the framework-free one (`asgi_app.py`, bare ASGI over the primitives
and nothing else) is **executed against every case in `CASES`** by this package's own suite. That
makes it the first of the three independent proofs §11.1 is designed to collect, and it makes the
table testable rather than aspirational today rather than when the framework drivers land. The
Django and FastAPI examples cannot be executed here — installing either framework would breach the
boundary — so they are parsed and symbol-checked against the public API, which catches the realistic
rot without importing a framework. That limitation is stated in the examples' own README.

**Not done, and deliberately:** the amendments in §A.1–A.3 were already applied to the django and
commons plans before this run. Phase 10 ships the *contract* only; the commons token-verification
module it names as a build-order predecessor does not exist yet, and nothing here imports it.
Nothing is committed.


## Summary (read this first)

Every module below is derived from two independent implementations. Where they disagree, this plan
picks one and says why — those calls are the real content here, not the code.

| Phase | Module | Prior art | Risk |
| --- | --- | --- | --- |
| 0 | Package scaffold + **dependency evaluation** | — | **blocking** |
| 1 | `context.py` — correlation ID (over `asgi-correlation-id` if it holds up) | cims `RequestIdMiddleware`, intellibench `correlation.py` | low |
| 2 | `problem.py` — RFC 9457 + exception→problem registry | cims `problem_details_handler`, intellibench `problem.py`/`error_mapping.py`/`handlers.py` | low |
| 3 | `concurrency.py` — ETag / `If-Match` | cims `enforce_version`, intellibench `concurrency.py` | low |
| 4 | `pagination.py` — opaque cursor codec, **AIP-158 spelling** | intellibench `ports/cursor.py` + `pagination.py` (cims is page-number; see §4) | low |
| 5 | `idempotency.py` — store protocol + request hashing | cims `idempotency.py`, intellibench `ports/idempotency.py` | low |
| 6 | `health.py` — check aggregation | cims `readyz`, intellibench `config/doctor.py` + `routers/health.py` | low |
| 7 | `asgi.py` — correlation middleware (wrapper or hand-rolled, per Phase 0) | intellibench `CorrelationIdMiddleware` | medium |
| 8 | Curated `__init__` + docs site | — | none |
| 9 | **Consumer context pack** — what app specs are written against | — | none |
| 10 | `auth.py` — `Principal`, authenticator/authorizer protocols, the 401/403 + `WWW-Authenticate` contract | both codebases' auth layers; RFC 6750/7617 | medium |
| 11 | `conformance/` — the scenario table both framework packages are tested against | — | low |

**Phases 10 and 11 were added after the first draft** and are numbered by arrival, not by execution
order. Run **Phase 10 before Phase 8** (its symbols belong in the curated `__init__`) and **Phase 11
alongside Phases 1-6**, adding each case in the same change as the decision it encodes. Phase 10 is
additionally blocked on the commons token-verification module (§10.1).

### Dependency policy for this package

The workspace principle (README / CLAUDE.md §Design principles) applies here in full: **if a proven
library does the job, depend on it and wrap it for a consistent syntax; do not reimplement it.** This
package is not "stdlib only" and must not be described that way.

What that means concretely, phase by phase:

- **Phase 1 + 7 (correlation ID):** [`asgi-correlation-id`](https://pypi.org/project/asgi-correlation-id/)
  (5.0.1 at time of writing, `>=3.10`) already ships the ContextVar, the pure-ASGI middleware, ID
  generation and validation, and a logging filter. Evaluate it in Phase 0 and **prefer it** — pykit
  contributes the naming, the frozen-dataclass config and the re-exports, not a second implementation.
- **Phase 2 (problem details):** [`rfc9457`](https://pypi.org/project/rfc9457/) (0.4.1) implements the
  problem shape framework-agnostically. Evaluate it; if its exception model composes with
  `AppException`, build the registry on top of it rather than defining the wire shape here.
- **Phases 3–6:** no maintained framework-agnostic library was found for ETag preconditions, opaque
  cursor pagination, idempotency-key stores or health aggregation. Phase 0 records that search;
  hand-rolling these is the exception the principle allows, not the default.
- **Logging:** `structlog` is the proven library, both surveyed apps use it, and this package must not
  reimplement structured logging. It also must not *import* it — see Convention 1. Whether commons
  adopts structlog is the commons plan's Phase 9 gate; this package's design is deliberately
  compatible with either outcome.

Every dependency added must be justified in the `pyproject.toml` comment beside it and in the package
README. A dependency that is only needed by one module goes behind an extra.

### Guiding principle for this plan

**Ship the shape both codebases converged on; parameterize where they disagreed; ship nothing neither
of them has.** Concretely:

- **Protocols here, adapters elsewhere.** `rn_forge.web` defines `IdempotencyStore` and never
  implements a real one (beyond an in-memory test double). Django implements it over the cache; a
  SQLAlchemy app implements it over its outbox table. Two adapter shapes are already known for every
  protocol this package declares — which is what makes declaring them safe rather than speculative.
- **No web-framework imports.** Not `django`, not `fastapi`, not `starlette`, not `rest_framework`.
  This is a boundary rule, not a dependency-count rule: a package that imports one framework cannot
  serve the other. A ruff/import check enforces it (Phase 0).
- **Wire shapes are dataclasses, not pydantic models.** Not because pydantic is a dependency to avoid
  — it is a fine library — but because a Django/DRF consumer would carry it for nothing while a
  FastAPI consumer can trivially mirror a dataclass as a `BaseModel`. `DataclassMixin` from commons
  gives serialization. Record this as a decision, not as a dependency ban.
- **Async-capable, not async-only.** One surveyed app is async end to end; Django is sync. Every
  protocol that could block declares an async method; every pure function is sync and usable from
  both. Where a helper takes a caller-supplied callable (health checks), it accepts sync or async and
  awaits what is awaitable.

### Three cross-cutting facts the survey established

These were read out of the two codebases and they constrain everything below.

1. **Both codebases use `structlog`,** with near-identical correlation processors (cims's
   `add_context`, intellibench's `bind_correlation_processor`). pykit's `AppLogger` is the odd one out
   at 2-to-0. This does not by itself settle what commons does (that is the commons plan's Phase 9
   gate), but it does settle this package: **nothing in `rn_forge.web` logs through `AppLogger`.**
   See Convention 1.
2. **The async/sync split is real and unavoidable.** intellibench's `IdempotencyStore.record_or_replay`
   is `async def` against `AsyncSession`; Django's equivalent is a sync cache call. A protocol with
   only one of the two shapes excludes one consumer outright.
3. **Both codebases already have their own `Settings`/config object** (`pydantic-settings` in
   intellibench, Django settings in cims), and the rewrites will too. This package therefore takes
   configuration as **constructor/parameter arguments** and owns no settings facade of its own.
   `rn-forge-django`'s settings facade wires the Django side.

### Conventions for this package

1. **Logging is injected, always — no exceptions in this package.** Unlike `rn-forge-django`, where
   `AppLogger` at module level is fine, *nothing* in `rn_forge.web` may import `AppLogger` at module
   scope. Anything that logs takes a `log: Callable[[str, Mapping[str, Any]], None] | None = None`
   parameter; when it is `None`, the module stays silent rather than falling back. A library that logs
   where the consumer did not ask is worse than one that does not log.
2. **Metrics are optional hooks, never a hard dependency.** Same rule the other plans state.
3. **Errors derive from `AppException`.** Every exception this package defines subclasses
   `rn_forge.commons.exceptions.AppException`, so a consumer already catching that catches these —
   including exceptions raised by a wrapped third-party library, which are translated at the wrapper
   boundary rather than leaking the library's own type.
4. **Curated `__init__.py`.** Unlike `rn_forge.django`, this package **does** have a curated top-level
   public API, following `rn_forge/commons/__init__.py`: every public symbol imported and listed in a
   sorted `__all__`. A wrapped library's symbols are re-exported under pykit names.
5. **Strict typing, `py.typed`, module docstrings, explicit `__all__`, `from __future__ import
   annotations`** — same as the rest of the workspace. Pyright strict covers this package
   automatically once it is under `packages/` (root `pyproject.toml` `include = ["packages"]`).
6. **Every module must be importable with the base install.** Anything needing an extra is guarded and
   tested both ways.

### Things deliberately NOT in this package

- **Page-number pagination.** DRF's `PageNumberPagination` is a Django concept, and cursor pagination
  is what an API over a live table actually needs. Cursor pagination lives here; the DRF page-number
  class stays in `rn-forge-django`.
- **Resilience (circuit breaker, retry, rate limiting) and the outbound HTTP client.** It stays in
  commons (commons plan Phase 8), and the reason is **dependency direction, not classification**.
  "Everything HTTP lives in `rn-forge-web`" is the tempting rule and it is wrong here:

  - A breaker, a retry policy and a token bucket are transport-agnostic — a worker retrying a DB
    call, a CLI retrying a blob upload and an LLM adapter backing off all need them, and none of them
    speaks server-side HTTP.
  - `rn-forge-azure` depends on **commons only** and needs exactly this (async breaker, token-bucket
    limiter, `Retry-After`-aware retry — see the Azure plan). Moving resilience here would make an
    Azure Blob/Key Vault/Service Bus adapter package depend on `rn-forge-web`, dragging ASGI
    middleware, problem registries and cursor codecs into a process that serves no HTTP at all.
  - This package is about **inbound** wire semantics — what a server promises its callers. The
    resilient client is **outbound** — how a caller survives someone else's server. They are mirror
    images, not the same concern, and they have different consumer sets.

  The genuinely shared vocabulary (`parse_retry_after`, transient-status classification) stays in
  commons, which this package already depends on, so nothing is duplicated and nothing inverts. The
  one exception runs the other way — see §2.5.
- **Multi-tenancy / row-level-security scoping.** intellibench's `ProjectScopedRepository` and its
  `before_execute` isolation hook are excellent and entirely SQLAlchemy-specific. Deferred, and
  recorded below.
- **Auth.** OIDC/JWKS verification is framework-agnostic and belongs in commons (it is pyjwt +
  httpx — identity, not HTTP wire shape). The `rn-forge-django` plan's Phase 9 should consume it from
  there.
- **`AuditContextMiddleware`-style header-trust auth bypass** (cims's `X-CIMS-Actor`). Same reasoning
  as the other plans: never normalize a dev-convenience bypass into a library.

### Package scaffold and dependencies

`packages/rn-forge-web/pyproject.toml`:

```toml
[project]
name = "rn-forge-web"
version = "0.1.0"
description = "Framework-agnostic HTTP/API primitives built on rn-forge-commons"
requires-python = ">=3.14"          # workspace floor; see Phase 0.1
dependencies = [
  # Pinned direct URL, not a bare name: these packages are not on PyPI and a release is a tag
  # (kiln D46). The `[tool.uv.sources]` override below is local development only.
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
  "rfc9457>=0.4.1",                 # phase 2 — RFC 9457 problem shape, if Phase 0 confirms the fit
]

[project.optional-dependencies]
asgi = ["asgi-correlation-id>=5.0.1"]   # phases 1 + 7 — correlation ContextVar + ASGI middleware
testing = ["assertpy>=1.1", "pytest>=9.1.1"]

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "rn_forge.web"

[tool.uv.sources]                   # local development only — see the alignment section, §3
rn-forge-commons = { workspace = true }
rn-forge-web = { workspace = true }

[tool.pytest.ini_options]
addopts = "-ra --import-mode=importlib"
markers = ["unit: fast isolated tests", "asyncio: async tests"]
```

Both third-party entries are **provisional on Phase 0's evaluation** — if either library does not fit,
drop it from this file along with the wrapper design that assumed it, and record why in the package
README. Do not carry a dependency that ends up wrapped in workarounds.

`asgi-correlation-id` sits behind an `asgi` extra rather than in the base dependencies because a
Django/WSGI consumer needs the pure functions in `context.py` and not the middleware. `context.py`
imports it lazily (or re-exports its ContextVar only when installed) so Convention 6 holds.

Root `pyproject.toml`: add `"packages/rn-forge-web"` to `[tool.uv.workspace] members`,
`rn-forge-web = { workspace = true }` to `[tool.uv.sources]`, and `rn-forge-web` to the `workspace`
dependency group. Pyright picks it up automatically via `include = ["packages"]`.

Dev group needs `pytest-asyncio` (Phase 7 and the async protocol tests) — the workspace does not have
it today; `asyncio_mode = "auto"` is the setting to use.

### Validation command for every phase

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-web
uv run ruff check packages/rn-forge-web
uv run ruff format --check packages/rn-forge-web
uv run pyright                       # strict; covers every package
uv run lint-imports                  # the boundary contracts — alignment §2
uv run --directory packages/rn-forge-web --group docs mkdocs build --strict
```

Plus the framework-boundary check from Phase 0, kept as a fast local signal. `lint-imports` above is
the authoritative one — it sees transitive imports, which a grep does not:

```bash
! grep -rnE '^\s*(import|from)\s+(django|fastapi|starlette|rest_framework)' \
    packages/rn-forge-web/src/
```

---

## Phase 0 — Scaffold and the dependency decisions

**This phase is blocking, and its hard part is not the scaffold.**

### 0.1 — The Python floor stays `>=3.14`

An earlier draft of this plan made lowering the workspace floor to 3.12 a blocking prerequisite,
because cims pins 3.12 and intellibench pins 3.13. That reasoning is void: both applications are being
rewritten, and the rewrites target the interpreter pykit ships on. Keep `requires-python = ">=3.14"`
on the new package, and leave `rn-forge-commons` and `rn-forge-django` where they are.

The one consequence worth keeping from that draft: the commons plan's Phase 0 replaces `logging.py`'s
PEP 758 parenthesis-free `except` with the parenthesized form. That is still worth doing — it costs
nothing and removes a gratuitous version gate — but it is no longer a prerequisite for anything here.

If a future consumer genuinely cannot move past 3.12, lowering the floor is a separate, project-wide
decision with its own gate. Do not pre-emptively design for it.

### 0.2 — Evaluate the candidate libraries (the actual blocking work)

Per the workspace principle, the default is to depend, not to reimplement. Two candidates must be
decided before any module is written, because each one changes what Phases 1, 2 and 7 contain:

**`asgi-correlation-id` (Phases 1 + 7).** Check, in a throwaway script:

1. Its `CorrelationIdMiddleware` is pure ASGI (not `BaseHTTPMiddleware`) — the property Phase 7 exists
   to preserve.
2. Its ContextVar is readable from a plain sync function, so Django/WSGI code can use `context.py`
   without an ASGI stack.
3. Header name, generator and validator are all configurable — Phase 1 needs `X-Correlation-ID` as the
   default and per-consumer overrides.
4. Whether it resets the ContextVar per request, and whether that interacts badly with exception
   handlers running outside the middleware (see Phase 1's note on reset semantics).
5. Its transitive dependency set is `starlette`-free (it advertises framework independence; verify,
   because a `starlette` dependency would break the boundary rule outright).

If 1–3 hold, **adopt it**: Phase 1 becomes a thin re-export + pykit-named wrapper, Phase 7 becomes a
configuration helper rather than a middleware implementation, and both phases shrink by most of their
content. If 5 fails, reject it and hand-roll as originally specified. Record the outcome in the
package README.

**`rfc9457` (Phase 2).** Check:

1. It has no framework dependency.
2. Its problem/exception types can subclass or compose with `AppException` without fighting it.
3. Extension members serialize flattened at the top level (RFC 9457 §3.2), or can be made to.
4. It is typed (`py.typed`) — a strict-mode package cannot carry an untyped core dependency without a
   stub shim.

If all four hold, the `ProblemDetail` dataclass in §2.1 is replaced by a wrapper over its type, and
Phase 2 keeps only the registry, the 5xx-detail policy and the two validation-error normalizers — the
parts no library has. If 2 or 4 fails, implement §2.1 as written and say so in the README.

**Also record the negative results.** For Phases 3–6 the search found nothing maintained and
framework-agnostic. Write that down in the package README with the date, so the next person does not
redo the search — and so that if a library appears later, the decision is visibly revisitable.

### 0.3 — Scaffold

Standard workspace-member layout, copied from `rn-forge-commons`:

```
packages/rn-forge-web/
  pyproject.toml
  README.md
  mkdocs.yml
  docs/{index.md,guides/,api/}
  src/rn_forge/web/{__init__.py,py.typed}
  tests/__init__.py
```

`mkdocs.yml` copies commons' verbatim except `site_name`/`site_description` — the mkdocstrings
handler config, `site_dir: .out/site` and `use_directory_urls: false` all carry over unchanged.

Add the two import-linter contracts from the alignment section (§2) to `.importlinter` and add
`rn_forge.web` to its `root_packages`. That file already exists and already gates CI — there is no
"nowhere to put it yet" any more, and the package README records the invariant in prose as well.

**Phase 0 exit criteria:** `uv sync --all-extras` resolves; `import rn_forge.web` works with and
without the `asgi` extra; `uv run pyright` clean; `uv run lint-imports` passes with the two new
contracts present; the framework-boundary grep returns nothing; both library evaluations decided and
written into the package README with their reasons.

---

## Phase 1 — `context.py`: the correlation ID

The smallest module and the one everything else reads. Both implementations exist; they differ on
three points and intellibench is right on all three.

**Read Phase 0.2 first.** If `asgi-correlation-id` passes its evaluation, most of this module is a
wrapper: its ContextVar is re-exported under pykit names, its generator/validator hooks are configured
through a frozen dataclass, and only the pieces it lacks are written by hand
(`require_correlation_id`, the reset-on-exit context manager for WSGI, and the log processor). The API
surface specified here is the same either way — that is the point of the wrapper — so the signatures
below are the contract regardless of what implements them.

**Sources.** cims `apps/common/middleware.py::RequestIdMiddleware` (header `X-Request-ID`, ContextVar,
reset in `finally`). intellibench `apps/api/src/intellibuild_api/correlation.py` (header
`X-Correlation-ID`, ContextVar, **deliberately never reset**, plus a structlog processor).

```python
DEFAULT_CORRELATION_HEADER: Final = "X-Correlation-ID"

correlation_id_var: ContextVar[str | None] = ContextVar("rn_forge_correlation_id", default=None)


def new_correlation_id() -> str:
    """Return a fresh correlation ID (a UUID4 hex string)."""


def set_correlation_id(value: str) -> None:
    """Bind *value* for the current context. See the no-reset note below."""


def get_correlation_id() -> str | None:
    """Return the bound correlation ID, or None outside a request."""


def require_correlation_id() -> str:
    """Return the bound correlation ID, raising AppException if none is bound."""
```

**The three disagreements, resolved:**

1. **Header name.** cims uses `X-Request-ID`, intellibench `X-Correlation-ID`. Neither is "correct".
   Ship `DEFAULT_CORRELATION_HEADER = "X-Correlation-ID"` (it is the name that survives across service
   hops, which is the actual use case) and make it a parameter everywhere it is read. The Django
   middleware keeps `X-Request-ID` as *its* default for backwards compatibility — that is a
   `rn-forge-django` decision — and per the "prior art, not compatibility" rule, that plan is amended
   to adopt `X-Correlation-ID` too (see §A.1). One header name across every app is the point.
2. **Reset or not.** cims resets the ContextVar token in a `finally`. intellibench deliberately does
   not, with a comment worth reproducing in full in the module docstring: a bare `Exception` handler
   is dispatched by Starlette's `ServerErrorMiddleware`, which sits *outside* every user-added
   middleware, so a `finally: reset()` in the middleware unsets the value before the handler that
   needs it runs. Since every request is its own task with its own copied context, leaving it bound
   leaks nothing. **Provide both**: `set_correlation_id()` (no token) for the ASGI case, and a
   `bind_correlation_id()` context manager that resets on exit for the sync/WSGI case where the same
   thread genuinely is reused. Document which is which and why, or the next person will "fix" one of
   them into the other.
3. **Both a getter that raises and one that does not.** intellibench's `get_correlation_id()` raises
   `RuntimeError` outside a request. That is right for its API-only usage and wrong for a library that
   might be called from a worker. Ship `get_correlation_id() -> str | None` and
   `require_correlation_id() -> str` (raising `AppException`), and let callers pick.

**Also ship** `correlation_log_processor(logger, method_name, event_dict)` — a structlog-shaped
processor that injects `correlation_id` when bound. It takes no structlog import (the signature is
just three positional arguments returning a mapping), which keeps the boundary rule intact while being
directly usable as `structlog.configure(processors=[correlation_log_processor, ...])`. Both surveyed
codebases hand-wrote exactly this; shipping it once is what stops the rewrites doing it a third time.
Say in the docstring that it is duck-typed against structlog's processor protocol, not an import of
it — and that duck-typing here is deliberate boundary-keeping, not dependency avoidance.

**Tests.** `tests/test_context.py` (`unit`): set/get round-trip; `get` returns `None` when unbound;
`require` raises when unbound; `bind_correlation_id` resets on exit and on exception;
`new_correlation_id` returns distinct values; the processor injects when bound and leaves the event
dict untouched when not; ContextVar isolation across two `asyncio.Task`s (the property intellibench's
no-reset design depends on — assert it rather than assuming it).

---

## Phase 2 — `problem.py`: RFC 9457 problem details and the exception registry

The highest-value module in the package. Both codebases built one; intellibench's is considerably
better designed and is the basis here.

**Read Phase 0.2 first.** If `rfc9457` passes its evaluation, §2.1's dataclass becomes a thin wrapper
over its problem type and this phase keeps only §2.2–§2.4 — the registry, the 5xx policy and the
normalizers, none of which any library provides. RFC 9457 obsoletes RFC 7807; the media type
`application/problem+json` and the member names are unchanged, so the wire shape below is correct
under either RFC number.

**Sources.** cims `apps/common/exceptions.py::problem_details_handler`. intellibench
`apps/api/src/intellibuild_api/problem.py` (the `ProblemDetail` shape and `problem_type(slug)`),
`error_mapping.py` (the `ErrorMapping` dataclass, the literal `MAPPING`, and `mapping_for`'s MRO
walk), `handlers.py` (`_problem_response`, `_status_mapping`, validation-error pointers).

### 2.1 — The wire shape

```python
PROBLEM_MEDIA_TYPE: Final = "application/problem+json"


@dataclass(frozen=True)
class ProblemDetail(DataclassMixin):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def as_body(self) -> dict[str, Any]:
        """Flatten to the wire body — extensions merged at the top level, per RFC 9457 §3.2."""
```

`extensions` is a nested field in Python and **flattened at the top level on the wire** — RFC 9457
(and RFC 7807 before it) puts extension members directly on the object, which is how both
implementations do it (intellibench's `body.update(extensions)`; its `correlation_id` is an extension, not a core member).
Keeping them nested in the dataclass is what makes `as_body()` the single place that knows the rule.

### 2.2 — The registry

intellibench's `MAPPING: dict[type[Exception], ErrorMapping]` plus `mapping_for`'s MRO walk is the
piece worth taking wholesale — it means an adapter subclass resolves to its base's row automatically,
which is exactly the behaviour you want and exactly the behaviour nobody remembers to build.

```python
@dataclass(frozen=True)
class ProblemType:
    slug: str
    status: int
    title: str


class ProblemRegistry:
    """Maps exception classes to problem types, resolving by MRO."""

    def __init__(
        self,
        *,
        type_base: str = "about:blank",
        fallback: ProblemType = INTERNAL_ERROR,
    ) -> None: ...

    def register(self, exc_type: type[BaseException], problem: ProblemType) -> Self: ...
    def problem_for(self, exc: BaseException) -> ProblemType: ...
    def build(
        self,
        exc: BaseException,
        *,
        instance: str,
        detail: str | None = None,
        extensions: Mapping[str, Any] | None = None,
    ) -> ProblemDetail: ...
```

Design calls:

- **An instantiable registry, not a module-level dict.** intellibench's `MAPPING` is a module global,
  which is correct for an application and wrong for a library — two apps in one process, or a test
  that wants a clean registry, both need instances. `register` returns `Self` for chaining, matching
  the commons idiom.
- **`type_base` defaults to `about:blank`.** intellibench builds `PROBLEM_TYPE_BASE + slug` from its
  own branding constant. A library must not invent a URI namespace; `about:blank` is what RFC 9457
  prescribes when there is no type URI. When `type_base` is set, `type` becomes `type_base + slug`.
- **Ship a default registry populated with the HTTP-status rows both implementations have** —
  `not-found`/404, `validation-error`/422, `internal-error`/500, `conflict`/409,
  `precondition-failed`/412, `precondition-required`/428, `unauthorized`/401, `forbidden`/403 — as
  `default_registry()`, a **factory returning a fresh instance**, never a shared module-level
  singleton a consumer could mutate out from under another.
- **`detail` for 5xx must not leak.** intellibench's `_catch_all` uses `str(exc)` below 500 and a
  generic string at 500+. Bake that into `build()`: when `status >= 500` and no explicit `detail` is
  passed, use a fixed generic message. This is the one piece of *policy* in the module, and it is
  policy worth having as the default because getting it wrong leaks internals.

### 2.3 — Normalizing validation errors

The two frameworks report field errors in two different shapes, and the library needs one:

- DRF: `{"field": ["msg", ...]}`, nested for nested serializers.
- FastAPI/pydantic: `[{"loc": ("body", "field"), "msg": "...", "type": "..."}, ...]`.

Both normalize to intellibench's shape, which is the better one because it is unambiguous under
nesting: `errors: [{"pointer": "/body/field", "message": "..."}]` — an RFC 6901 JSON pointer.

```python
def errors_from_pointer_list(raw: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Normalize a FastAPI/pydantic error list (loc/msg) into pointer/message pairs."""


def errors_from_field_map(raw: Mapping[str, Any]) -> list[dict[str, str]]:
    """Normalize a DRF-style {field: [messages]} map, recursing into nested maps."""
```

The DRF one must recurse — nested serializers produce nested dicts and lists, and a non-recursive
version silently drops every nested error. cims's handler does not recurse; that is a bug being
fixed on the way through, not a behaviour to preserve.

### 2.4 — Conflict exceptions

This resolves an open question from the django plan, which put these in `rn_forge/django/exceptions.py`
on the grounds that commons had no caller. **They belong here**, in
`rn_forge/web/exceptions.py` or alongside the registry:

```python
class WebError(AppException): ...
class DomainConflict(WebError): ...          # 409
class VersionConflict(DomainConflict): ...    # 412 — see Phase 3
class PreconditionRequired(WebError): ...     # 428
class MalformedPrecondition(WebError): ...    # 400
class InvalidCursor(WebError): ...            # 400
class IdempotencyKeyRequired(WebError): ...   # 400
class IdempotencyKeyReuse(WebError): ...      # 409
```

`default_registry()` registers all of them. This mirrors intellibench's `api_errors.py` almost
exactly — the difference is that intellibench keeps them in the app because they "never cross a port
boundary", which is true for one app and false for a library whose whole job is to be the shared
boundary that several apps meet at.

### 2.5 — Client-side parsing (the piece that belongs here, not in commons)

Everything above builds a problem body. Services in this kit will also **consume** each other's, and
that is genuinely this package's concern rather than the resilient client's: the commons
`ResilientHttpClient` knows about transport failures and status codes, not about
`application/problem+json`.

```python
def problem_from_body(status: int, body: Mapping[str, Any]) -> ProblemDetail:
    """Parse a problem+json body back into a ProblemDetail, tolerating missing members."""


class RemoteProblem(WebError):
    """A problem returned by an upstream service. Carries the parsed ProblemDetail."""
```

Design calls:

- **Tolerant on the way in, strict on the way out.** RFC 9457 requires only that the body be a JSON
  object; every member is optional in practice and upstreams get this wrong. Missing `type` defaults
  to `about:blank`, missing `status` falls back to the HTTP status argument, unknown members land in
  `extensions`. A parser that raises on a slightly-wrong body converts an upstream 404 into a local
  500.
- **It takes a parsed mapping and a status, not a response object.** No `httpx` import, no
  `requests` import — the caller unwraps its own client's response. This keeps the module usable from
  a commons `ResilientHttpClient` call site, a Django test, or an async FastAPI client without any of
  them being a dependency here.
- **`RemoteProblem` is the seam that stops error detail being lost.** An upstream `conflict`/409
  becomes a typed local exception carrying the original slug, so a gateway can re-emit it rather than
  flattening every upstream failure into "internal error".

This is the only direction in which HTTP-client concerns move *toward* this package, and it moves as
a pure function over a mapping precisely so the direction of the dependency arrow never changes.

**Tests.** `tests/test_problem.py` (`unit`): `as_body` flattening including an extension colliding
with a core member (define and assert the precedence — core members win); MRO resolution to a base
class row; unregistered exception → fallback; `type_base` applied and absent; 5xx detail suppression
and explicit-detail override; both normalizers including nested DRF maps and multi-segment pydantic
`loc`; `default_registry()` returns independent instances.

---

## Phase 3 — `concurrency.py`: ETag and `If-Match`

**Sources.** cims `apps/common/concurrency.py::enforce_version` (reads `If-Match`, strips weak-ETag
quoting, falls back to a `version` body key, raises `VersionConflict` → **409**). intellibench
`apps/api/src/intellibuild_api/concurrency.py` (`etag_for(entity_id, version)` producing
`W/"<uuid>:<version>"`, a strict regex `parse_if_match`, `require_if_match` → **428** when absent,
mismatch → **412**).

### 3.1 — The status-code disagreement, resolved

cims returns **409 Conflict**; intellibench returns **412 Precondition Failed** for a mismatch and
**428 Precondition Required** when the header is absent on a route that demands it. **intellibench is
correct** — RFC 9110 §15.5.13 defines 412 as precisely "the precondition given evaluated to false on
the server", and RFC 6585 defines 428 for the required-but-absent case. 409 is for a conflict with
the resource's state generally, which is a superset.

So: `VersionConflict` registers as **412** in `default_registry()`, `PreconditionRequired` as **428**,
and `DomainConflict` keeps **409** for genuine state conflicts. The `rn-forge-django` plan's Phase 1,
which said "map `DomainConflict`/`VersionConflict` → HTTP 409", is amended accordingly (see below).
A consumer that genuinely needs 409 here re-registers `VersionConflict` on its own registry instance —
one line, which is the payoff for the registry being instantiable. No app should need to.

### 3.2 — The validator-format disagreement, resolved

cims's validator carries only a version (`W/"7"`); intellibench's carries entity and version
(`W/"<uuid>:<version>"`). intellibench's is strictly more useful — it catches a client replaying a
precondition from a *different* entity — but it forces a UUID PK, which `rn_forge.django.BaseModel`
does not have. So make the codec pluggable, and ship both:

```python
class ETagCodec(Protocol):
    def format(self, *, entity_id: object, version: int) -> str: ...
    def parse(self, raw: str) -> tuple[str | None, int]: ...
        """Return (entity_id or None, version). Raise MalformedPrecondition on anything else."""


class VersionETagCodec:
    """W/"<version>" — carries no entity identity. For models without a stable public id."""


class EntityVersionETagCodec:
    """W/"<entity_id>:<version>" — the default; catches a precondition replayed across entities."""
```

`EntityVersionETagCodec` is the default. Its parse regex must **not** hardcode a UUID pattern the way
intellibench's `[0-9a-fA-F-]{36}` does — accept any non-`:`-containing identifier, since integer and
slug primary keys are both real. Note this relaxation in the docstring; it is deliberate, not sloppy.

### 3.3 — The functions

```python
def check_precondition(
    raw_if_match: str | None,
    *,
    current_version: int,
    entity_id: object | None = None,
    codec: ETagCodec = ...,
    required: bool = False,
) -> None:
    """Raise unless the client's precondition matches the current state."""
```

- `raw_if_match is None` and `required` → `PreconditionRequired` (428).
- `raw_if_match is None` and not `required` → pass silently. cims does this; keep it, and document
  that making preconditions mandatory is the caller's choice.
- Malformed → `MalformedPrecondition` (400), never a crash. intellibench's docstring says
  "deliberately strict — anything else is a 400, never a crash"; that sentence belongs in ours.
- Version mismatch, or entity mismatch when the codec carries an entity → `VersionConflict` (412).
- Handle `If-Match: *` (RFC 9110: matches any current representation) → pass. Neither implementation
  does; both are wrong on it, and it costs two lines.

**Deliberately not here:** the body-key fallback (cims reads `version` from the request body when the
header is absent). That is a per-framework request-parsing concern and it weakens the precondition
contract. `rn-forge-django` can keep it as its own convenience, reading the body itself and calling
`check_precondition` with the resulting string.

**Tests.** `tests/test_concurrency.py` (`unit`): round-trip both codecs; match passes; version
mismatch raises 412's exception; entity mismatch raises; absent + `required` raises 428's; absent +
not required passes; `*` passes; malformed forms (no `W/`, unquoted, non-integer version, missing
colon) each raise `MalformedPrecondition`; a strong (non-weak) ETag — decide whether to accept and
test the decision either way.

---

## Phase 4 — `pagination.py`: opaque cursors, in AIP-158's spelling

Only intellibench has this; cims uses DRF page-number pagination. That made this the one module with
a single source, and **that is no longer an acceptable basis for a shared package** — a module in
`rn-forge-web` with one consumer is a FastAPI module parked in the wrong place. The resolution is not
to drop it but to make it the standard on both sides: django plan Phase 2 is amended to ship a
`CursorPagination` over this codec as its *standard* pagination class, with page-number demoted to an
explicitly legacy option (see §A.1). Until that amendment is executed, this module has no Django
consumer and the dedupe claim for it is unproven.

**Sources.** intellibench `libs/backend/ports/src/intellibuild_ports/cursor.py` (base64 over
`{"k": sort_key, "id": entity_id}`) and `apps/api/src/intellibuild_api/pagination.py` (`Page[T]`,
`cursor_params(cap)` clamping rather than rejecting).

### 4.1 — The wire spelling is Google AIP-158, not ours

There is no IETF standard for pagination. [AIP-158](https://google.aip.dev/158) is the de facto
convention for modern REST APIs and for the OpenAPI generators that read them, and it is worth
adopting wholesale rather than inventing a spelling, for one specific reason: **it independently
reached the same non-obvious decision this plan did.** AIP-158 on `page_size`: *"if the user gives a
`page_size` greater than the maximum, the service should coerce down to the maximum"* — clamp, never
reject, which is exactly intellibench's rule and exactly what a FastAPI `Query(le=...)` would
violate. When a standard and an independent implementation agree, the standard wins the naming.

The contract, and it is normative for **both** framework packages:

| Direction | JSON / query name | Python name | Meaning |
| --- | --- | --- | --- |
| request | `pageSize` | `page_size` | requested page size; clamped server-side to the cap, never rejected |
| request | `pageToken` | `page_token` | opaque continuation token; absent means first page |
| response | `nextPageToken` | `next_page_token` | opaque; absent or `null` means the last page |
| response | `items` | `items` | the page's elements |
| response | `totalSize` | `total_size` | **optional**, off by default — a keyset query cannot cheaply count |

Three notes that stop this drifting:

- **The token is opaque and must be documented as such.** AIP-158 is explicit that a client must not
  parse it. Keeping it opaque is what lets the codec change without a client change — and it is why
  no signing is added (a cursor is opaque, not secret; signing means key management).
- **AIP-158 names the response array after the resource** (`users`, `builds`). A library cannot, so
  this package fixes it at `items` and records the deviation here. A generated client then has one
  page type rather than one per resource, which is the better trade for a shared kit.
- **`totalSize` is off by default.** Page-number pagination gives a total for free and keyset does
  not; a UI that needs one must opt in per-endpoint and pay for the count. Do not make it the default
  to ease a migration from page-number.

### 4.2 — Additionally emit RFC 8288 `Link`

[RFC 8288](https://www.rfc-editor.org/rfc/rfc8288) Web Linking is a real IETF standard and is what
GitHub and GitLab use for pagination. Emitting `Link: <...?pageToken=...>; rel="next"` alongside
`nextPageToken` costs a few lines, serves clients that were not generated from the schema, and
contradicts nothing. **Additive, never a replacement** — the body field is the contract; the header is
a convenience, and a client relying only on the header will break on an endpoint that cannot build an
absolute URL.

### 4.3 — The module

```python
@dataclass(frozen=True)
class Cursor:
    sort_key: str
    entity_id: str


def encode_cursor(sort_key: str, entity_id: str) -> str: ...
def decode_cursor(raw: str) -> Cursor:
    """Raise InvalidCursor on anything not a well-formed cursor."""


@dataclass(frozen=True)
class Page[T](DataclassMixin):
    items: Sequence[T]
    next_page_token: str | None
    total_size: int | None = None


def clamp_page_size(requested: int | None, *, default: int, cap: int) -> int:
    """Clamp server-side; never reject an over-large page size (AIP-158)."""


def next_link_header(base_url: str, token: str, *, param: str = "pageToken") -> str:
    """Build an RFC 8288 `Link: <...>; rel="next"` value. §4.2."""
```

`Page.limit` from the earlier draft is gone — it duplicated the request parameter in the response for
no consumer. `clamp_limit` is renamed `clamp_page_size` to match the wire name; there is no
compatibility alias, per the workspace rule.

Design calls carried over unchanged:

- **Keep it `urlsafe_b64encode` over compact JSON**, exactly as intellibench has it.
- **Catch the same exception set intellibench does** on decode: `ValueError`, `KeyError`, `TypeError`,
  `binascii.Error`, `json.JSONDecodeError`. Missing one turns a tampered cursor into a 500.
- **`Page` is generic via PEP 695** (`class Page[T]`), matching the syntax already used elsewhere in
  the workspace (`rn_forge/django/auth/drf/authentication.py:36`).

**One decision for the implementer, not for this plan.** DRF's own `CursorPagination` carries a
`reverse` flag in its cursor so it can serve a previous page; AIP-158 is forward-only and this
`Cursor` has no such field. Django Phase 2 wraps DRF's keyset machinery (§A.1), so it must either
add `reverse: bool = False` to `Cursor` — three lines here, and FastAPI simply never sets it — or
disable reverse paging on the Django side. **Decide it in django Phase 2 and record it**; do not let
the two packages answer it differently, because a `previousPageToken` on one stack and not the other
is precisely the divergence this package exists to prevent.

> **Decided in django Phase 2 (2026-09-12): forward-only on both stacks.** `Cursor` gains no
> `reverse` field; `rn_forge.django.drf.pagination.CursorPagination` emits no `previousPageToken`,
> exactly as `rn-forge-fastapi` does not. AIP-158 is forward-only, and adding the field would have
> been a web change serving one stack. Recorded in the django plan too.

**Not here:** the actual keyset SQL. Turning `Cursor` into a `WHERE (sort_key, id) > (?, ?)` predicate
is ORM-specific — Django ORM in `rn-forge-django`, SQLAlchemy in the deferred `rn-forge-sqlalchemy`.

**Tests.** `tests/test_pagination.py` (`unit`): round-trip; every malformed input class (not base64,
base64 of non-JSON, JSON missing a key, JSON of a non-object) raises `InvalidCursor`;
`clamp_page_size` at, below and above the cap and with `None`; `Page` serializes through
`DataclassMixin` with `next_page_token` present and absent; `total_size` omitted from the body when
`None` rather than serialized as `null`; `next_link_header` produces a parseable RFC 8288 value.

---


## Phase 5 — `idempotency.py`: the store protocol

Both consumers have one, and their designs differ substantially. intellibench's is strictly stronger
and becomes the protocol; cims's becomes one adapter shape.

**Sources.** cims `apps/common/idempotency.py` (`replay`/`remember` over the Django cache, keyed
`idempotency:{scope}:{key}`, no body hashing, 24h TTL). intellibench
`libs/backend/ports/src/intellibuild_ports/idempotency.py` (`IdempotencyStore` ABC, `StoredResponse`,
`request_hash`, `IdempotencyKeyReuseError`) plus its `MutationOutboxIdempotencyStore` adapter using
`INSERT ... ON CONFLICT DO NOTHING` against a `UNIQUE (project_id, idempotency_key)` constraint.

### 5.1 — What intellibench has that cims does not

Three things, all of which go into the protocol:

1. **Body hashing.** `request_hash` canonicalizes the body (`json.dumps(sort_keys=True,
   separators=(",", ":"))`) and SHA-256s it, so replaying a key with a *different* body is a
   detectable client bug (`IdempotencyKeyReuse`, 409) rather than a silently-wrong cached response.
   cims cannot detect this at all. This is the single most valuable thing in the module.
2. **A two-phase protocol.** `record_or_replay` returns `None` on first sight (caller executes, then
   calls `complete`), or the stored response on replay. cims's `replay`/`remember` pair is the same
   idea without the atomicity: the claim and the completion are separate cache writes with no
   constraint tying them, so two concurrent first-sight requests both execute.
3. **Race-safety via a uniqueness constraint**, not check-then-insert. The docstring is explicit:
   "relies on the constraint rather than a check-then-insert race — two concurrent identical requests
   both reach the same row, one wins the insert, both read it back." A cache-backed adapter needs
   `cache.add()` (atomic set-if-absent) to get the same property; note that in the protocol docstring
   as an implementer requirement, because a `get`-then-`set` adapter silently loses it.

### 5.2 — The protocol

```python
def request_hash(body: Any) -> str:
    """SHA-256 over a canonical JSON encoding of *body*."""


@dataclass(frozen=True)
class StoredResponse(DataclassMixin):
    status: int
    body: Mapping[str, Any]
    replayed: bool = False


class IdempotencyStore(Protocol):
    def record_or_replay(self, *, scope: str, key: str, request_body: Any) -> StoredResponse | None: ...
    def complete(self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]) -> None: ...


class AsyncIdempotencyStore(Protocol):
    async def record_or_replay(...) -> StoredResponse | None: ...
    async def complete(...) -> None: ...
```

- **Both a sync and an async protocol.** Per cross-cutting fact 3 — intellibench's implementation is
  `async def` over `AsyncSession`, Django's will be a sync cache call. Two `Protocol`s with identical
  method shapes is the honest way to express that; a single protocol with `Awaitable[...] | ...`
  returns is not.
- **`scope`, not `project_id`.** intellibench's key is `(project_id, idempotency_key)` — its
  multi-tenancy leaking into the signature. Generalize to an opaque `scope: str`, which cims already
  has for a different reason (preventing cross-endpoint key collisions). A tenant-scoped consumer
  passes the tenant id in `scope`; an endpoint-scoped one passes the route name.
- **`InMemoryIdempotencyStore`** ships here as the test double implementing both protocols, the same
  way intellibench ships `InMemorySorCacheStore` beside its SQL one.

**Tests.** `tests/test_idempotency.py` (`unit`): `request_hash` is key-order-independent and
type-stable; first sight returns `None`; replay after `complete` returns `replayed=True` with the
stored status and body; the same key with a different body raises `IdempotencyKeyReuse`; distinct
`scope` values do not collide; replay before `complete` (in-flight) returns `None` — decide and
document whether that is right or should be a distinct "in progress" signal, because it is the one
genuinely ambiguous case and intellibench's version returns `None` for it.

---

## Phase 6 — `health.py`: check aggregation

**Sources.** cims `apps/common/views.py::readyz` (a dict of per-dependency checks, aggregate status,
503 on required failure, `SERVICE_BUS_REQUIRED` flag). intellibench
`libs/backend/config/src/intellibuild_config/doctor.py` (`CheckResult` with a four-value status —
`pass`/`warn`/`fail`/**`skipped`** — plus `remediation` and `reason`) and its `routers/health.py`
(`/healthz` liveness vs `/readyz` readiness, 503 when migrations are not at head).

intellibench's richer result shape wins:

```python
type CheckStatus = Literal["pass", "warn", "fail", "skipped"]


@dataclass(frozen=True)
class CheckResult(DataclassMixin):
    status: CheckStatus
    reason: str | None = None
    remediation: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


type Check = Callable[[], CheckResult | bool | Awaitable[CheckResult | bool]]


@dataclass(frozen=True)
class HealthReport(DataclassMixin):
    status: CheckStatus
    checks: Mapping[str, CheckResult]
    http_status: int


async def run_checks(checks: Mapping[str, Check], *, required: Collection[str] = ()) -> HealthReport: ...
def run_checks_sync(checks: Mapping[str, Check], *, required: Collection[str] = ()) -> HealthReport: ...
```

Design calls:

- **Four statuses, not a bool.** `skipped` is the one nobody invents on their own and the one that
  matters: intellibench reports not-yet-implemented check groups as `skipped` with the reason, "so
  absence is visible rather than silent". That is a genuinely good idea and it costs nothing.
- **A check may return `bool`** and it is coerced (`True` → `pass`, `False` → `fail`). Not for
  backwards compatibility — a one-line `lambda: db_reachable()` check should not have to construct a
  `CheckResult` to say "fine".
- **Every check is wrapped.** A raising check becomes `fail` with `reason=str(exc)`. intellibench's
  doctor says it outright: "A doctor check reports a failure; it must never itself crash the run."
  A readiness endpoint that 500s tells a load balancer nothing.
- **`required` drives the HTTP status.** A `fail` in `required` → 503. A `fail` outside it → the
  overall status degrades but `http_status` stays 200. `warn` never changes `http_status`. This is
  cims's `SERVICE_BUS_REQUIRED` concept generalized, and it is why the report carries `http_status`
  rather than making each framework re-derive it.
- **Both an async and a sync runner**, since checks may be either. `run_checks` awaits awaitable
  results; `run_checks_sync` raises `AppException` if handed an awaitable, rather than silently
  reporting a coroutine object as passing — which is exactly the bug that would otherwise ship.
- **Run checks concurrently** in the async runner (`asyncio.gather`); a readiness endpoint that
  serially awaits five 2-second timeouts is a ten-second readiness endpoint.

**Not here:** the endpoints. Django gets `readiness_view(...)`; FastAPI gets a router factory. Also
not here: liveness. `/healthz` returns 200 unconditionally and needs no library.

**Tests.** `tests/test_health.py`: all-pass → 200; required fail → 503; non-required fail → 200 with
degraded status; `warn` → 200; `skipped` recorded and ignored for status; raising check captured with
its message; bool coercion both ways; async and sync checks in one map; `run_checks_sync` given an
async check raises; empty map → 200; concurrency (two slow async checks finish in about the time of
one — use a fake clock or just assert both ran, not wall time).

---

## Phase 7 — `asgi.py`: the correlation middleware

The one place this package touches a protocol rather than pure data. It is here rather than in a
future `rn-forge-fastapi` because **ASGI is a specification, not a framework** — this middleware works
under FastAPI, Starlette, Litestar, Quart or a bare ASGI app.

**Read Phase 0.2 first.** If `asgi-correlation-id` was adopted, this phase is *not* a middleware
implementation: it is a factory that constructs that library's middleware with pykit's defaults
(header name, generator, log-processor wiring) and re-exports it under a pykit name. Write the
middleware by hand **only** if Phase 0 rejected the library. The specification below is what to build
in that case, and it doubles as the behavioural contract the wrapper is tested against.

**Source.** intellibench `apps/api/src/intellibuild_api/correlation.py::CorrelationIdMiddleware`.

```python
class CorrelationIdMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = DEFAULT_CORRELATION_HEADER,
        generator: Callable[[], str] = new_correlation_id,
    ) -> None: ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...
```

Behaviour, carried over as-is because it is already right:

- Pass through non-`http` scopes untouched (`websocket`, `lifespan`) before doing anything.
- Read the inbound header; generate when absent. **Never replace a caller-supplied ID** — that
  sentence is in intellibench's docstring and it is the whole contract.
- Wrap `send` to stamp the header on `http.response.start`.
- Bind the ContextVar with a plain `set()`, no reset — Phase 1's design note explains why, and that
  explanation must be reproduced here or someone will add a `finally`.

**Two things to get right that intellibench got right and are easy to lose:**

1. **Not `BaseHTTPMiddleware`.** Starlette's `BaseHTTPMiddleware` runs the downstream app in a spawned
   task, and a ContextVar set in `dispatch()` is documented not to reliably propagate into exception
   handlers invoked from that task. A pure ASGI middleware setting the value around `self.app(...)`
   has no such gap. Since we cannot import `BaseHTTPMiddleware` here anyway, the risk is that a
   consumer wraps ours in one — say so in the docs.
2. **Typing without Starlette.** `Scope`, `Receive`, `Send`, `ASGIApp` come from
   `starlette.types` in intellibench. Define them locally as type aliases
   (`type Scope = MutableMapping[str, Any]`, `type Message = MutableMapping[str, Any]`,
   `type Receive = Callable[[], Awaitable[Message]]`, and so on). This is ~6 lines and it is what
   keeps the *boundary* rule — importing `starlette.types` would make a Django consumer install
   Starlette. If a maintained, framework-free ASGI typing package turns up, use it instead; `asgiref`
   is not it (Django-adjacent machinery for six aliases).

Header manipulation on the raw scope: request headers are a list of `(bytes, bytes)` pairs under
`scope["headers"]`, compared case-insensitively after lowercasing; response headers are the same
under `message["headers"]`. Write a tiny `_get_header`/`_set_header` pair and test them directly —
this is the fiddly part and the part a Starlette import would have hidden.

**Tests.** `tests/test_asgi.py` (async): inbound header preserved through to the response; absent
header generated and stamped; ContextVar readable from inside the wrapped app; non-`http` scope
passed through untouched with no ContextVar set; custom `header_name` and `generator` honoured;
header comparison is case-insensitive; the middleware does not duplicate an existing response header.
Use a hand-written stub ASGI app — do not add Starlette as a test dependency, or the boundary the
whole phase exists to protect becomes untested. These tests are written against public behaviour, so
they apply unchanged whether the implementation is ours or a wrapped library's.

---

## Phase 8 — Public API and docs

1. `src/rn_forge/web/__init__.py` imports and re-exports every public symbol from all seven modules,
   `__all__` sorted, matching `rn_forge/commons/__init__.py`'s style.
2. `docs/index.md`, `docs/guides/{installation,quickstart}.md`, `docs/api/*.md` (one page per module)
   and the `mkdocs.yml` nav. Because `mkdocs build --strict` fails on a nav entry with no file, add
   each page in the same commit as its module rather than all at the end.
3. One guide worth writing by hand: **"Wiring rn-forge-web into FastAPI"** and **"…into Django"**,
   each about a page, showing the adapter layer each framework needs. These two pages are the proof
   that the package boundary is right — if either is longer than a page, the split is wrong and this
   plan should be revisited.
4. Add the package to the root docs monorepo config if the root `docs` group's
   `mkdocs-monorepo-plugin` aggregates the per-package sites.
5. A **"Dependencies and why"** README section: each third-party package, what it does, why it beat
   hand-rolling, and the negative results from Phase 0.2 (the concerns for which no library was
   found). This is what keeps the design principle auditable a year from now.

---

## Phase 9 — The consumer context pack

**This phase is a deliverable, not documentation garnish.** Both surveyed applications are being
respecified and reimplemented. The failure mode this whole package exists to prevent is each rewrite
re-deriving correlation IDs, problem bodies, cursors and idempotency semantics in its own dialect. That
is prevented by handing the spec authors something small enough to read and specific enough to write
against — not by hoping they find the API docs.

Ship, under `packages/rn-forge-web/docs/adoption/`:

1. **`api-conventions.md` — the wire contract, one page.** The exact things every app built on this
   kit must do identically: `X-Correlation-ID` in and out on every request; errors as
   `application/problem+json` with the registry's slugs and status codes (including 412/428 for
   preconditions); AIP-158 cursor pagination (`pageSize`/`pageToken`/`nextPageToken`) with the page
   size clamped, never rejected; `Idempotency-Key` on unsafe endpoints with body-hash reuse
   detection; `/healthz` vs `/readyz` semantics and when each returns 503; the 401/403 boundary and
   the `WWW-Authenticate` challenge (Phase 10.4). Written so it can be pasted into an application's
   specification as a normative section.

   **It must also carry the two conventions that are not tied to one module**, because they are what
   decides whether a client generated against one stack works against the other:

   - **Field casing: camelCase on the wire, `snake_case` in Python.** This is the Google JSON Style
     Guide's rule, Microsoft's REST API Guidelines' rule, and what proto3's JSON mapping produces —
     which is also why AIP-158's `page_size` appears here as `pageSize`. It is what every TypeScript
     client and every popular UI framework's HTTP layer expects, and picking either casing is far
     better than letting it vary per application. RFC 9457's core members (`type`, `title`, `status`,
     `detail`, `instance`) are single lowercase words and are unaffected; problem *extensions* follow
     the rule. Headers are exempt — HTTP field names are case-insensitive and hyphenated.

     **Both framework packages enforce this in code, not in a recipe.** The django plan's Phase 12 is
     amended from docs-only accordingly (§A.1), and the fastapi plan's Phase 2 ships the alias
     generator. A convention that only a guide enforces is a convention that holds until the first
     hurried endpoint.

   - **OpenAPI: the generated client is the real interface.** Both packages emit **OpenAPI 3.1.0**
     (JSON Schema 2020-12), both name the shared shapes identically in `components/schemas`
     (`ProblemDetail`, `Page`, `CheckResult`, `HealthReport`), and both follow one `operationId`
     convention — `operationId` is what a generator turns into a client method name, so two stacks
     that differ there produce two different client call sites for the same endpoint even when every
     byte of JSON matches. Name the convention in this document and let each package implement it.
2. **`wiring-django.md`** and **`wiring-fastapi.md`** — Phase 8.3's two guides, which double as the
   adoption path. Each shows the full adapter layer for one framework: settings, middleware,
   exception-handler registration, the idempotency store adapter, health-check registration.
3. **`checklist.md`** — a per-app checklist ("does this app use `rn_forge.web.problem` for *every*
   error response, or does it still hand-build one anywhere?"), so an app's own review can catch
   divergence rather than discovering it at integration time.
4. **A worked minimal example per framework** (~100 lines each, in `docs/adoption/examples/`), runnable
   and exercised by a test so it cannot rot. A spec author copies this; a prose guide they re-imagine.
5. **`model-conventions.md` — the persistence vocabulary, one page.** The unification boundary above
   rules out a shared model base class or repository protocol, permanently. What *is* shared is the
   vocabulary each ORM's base class conforms to without sharing code, and writing it down is what
   stops `rn_forge.django.BaseModel` and the deferred SQLAlchemy base drifting into two dialects of
   the same idea:

   - **Audit columns** — `created_by` / `created_at` / `updated_by` / `updated_at`, their types, and
     which are nullable. (`rn-forge-django` maps these to camelCase DB columns for legacy reasons;
     that mapping is a Django-side detail and must not leak into this vocabulary.)
   - **`status`** — the shared `Status` enum values and what each means.
   - **Optimistic concurrency** — the column is named `version`, it is a monotonically increasing
     `int`, and it is bumped on every write. This is the one entry with teeth: `check_precondition`
     (§3.3) and both `VersionedModelMixin` equivalents depend on it, and the `Versioned` protocol
     (`pk`, `version`) is the only structural type this package declares over a persisted object.
   - **Natural keys** — what a natural key is and how it is declared, since both ORMs need one for
     fixtures and neither agrees on the spelling by default.
   - **Soft delete and timestamps** — whether deletion is a status transition or a column, decided
     once here rather than twice.

   This page is *normative for the two ORM packages and advisory for applications.* It ships no code.

**Exit criterion for both normative pages:** the Phase 11 conformance table encodes every claim in
`api-conventions.md` that is observable on the wire. A convention stated in prose and absent from the
table is a convention that will drift.

Explicitly in scope for a *future* app too: nothing here may name cims or intellibench, or assume their
domains. If a sentence only makes sense for one of them, it belongs in that app's repository.

**Exit criterion:** someone writing an application specification can produce the API-behaviour section
of that spec from `api-conventions.md` alone, without reading this plan or any module source.

---

## Phase 10 — `auth.py`: the authentication contract

**Why this is here and was not before.** The earlier draft sent auth wholesale to commons — "OIDC/JWKS
verification is framework-agnostic and belongs in commons (it is pyjwt + httpx — identity, not HTTP
wire shape)". That reasoning is correct and it is incomplete: it covers *verifying a token* and says
nothing about *what a caller sees when verification fails*. A 401 body, the `WWW-Authenticate`
challenge and the 401-vs-403 boundary are wire semantics in exactly the sense the other six modules
are, and they are the part a UI cannot paper over. So the concern splits across three layers rather
than landing in one.

### 10.1 — The three-layer split

| Layer | Owns | Standards |
| --- | --- | --- |
| `rn-forge-commons` | Token *verification*: JWKS fetch/cache/rotation, JWT signature and claims validation, OIDC discovery. No HTTP-server concept. | RFC 7519, RFC 7517, RFC 8414, OIDC Discovery 1.0 |
| **`rn-forge-web` (here)** | The *contract*: `Principal`, the authenticator/authorizer protocols, and the failure wire shape — status, problem slug and `WWW-Authenticate`. | RFC 6750 §3, RFC 7617, RFC 9457 |
| `rn-forge-django` / `rn-forge-fastapi` | The *binding* only: a DRF `BaseAuthentication` / a FastAPI `Security` dependency, each producing the same `Principal`. | — |

The commons half is the module the django plan's Phase 9 and the fastapi plan already point at; this
phase does not build it, it declares what it must return. **Build order: the commons verification
module first, this phase second, the two bindings third.**

### 10.2 — `Principal`

```python
@dataclass(frozen=True)
class Principal(DataclassMixin):
    subject: str
    issuer: str | None = None
    scopes: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    tenant: str | None = None
    claims: Mapping[str, Any] = field(default_factory=dict)
    mechanism: str = "bearer"        # bearer | basic | saml | session
```

- **`subject` is the only required field**, and it is `sub` for OIDC, the username for basic, the
  `NameID` for SAML. Everything else is optional because no mechanism supplies all of it.
- **`scopes` and `roles` are separate** and both are `frozenset`. OAuth issues scopes; enterprise
  directories issue roles/groups; conflating them forces one to be encoded as the other.
- **`claims` carries the raw verified claim set** so an application can read something the library
  never modelled, without this dataclass growing a field per deployment.
- **`mechanism` exists so a problem body and an audit log can say how the caller authenticated**
  without the framework layer inventing its own vocabulary for it.

### 10.3 — Protocols

```python
class Authenticator(Protocol):
    def authenticate(self, *, credentials: Credentials) -> Principal: ...

class AsyncAuthenticator(Protocol):
    async def authenticate(self, *, credentials: Credentials) -> Principal: ...

class Authorizer(Protocol):
    def authorize(self, principal: Principal, *, requires: Requirement) -> None: ...
```

Both a sync and an async authenticator, for the same reason the idempotency store has both (§5.2): a
JWKS-backed verifier does network I/O and Django's is sync. `Requirement` is a small frozen dataclass
of `any_scope` / `all_scopes` / `any_role` / `all_roles` sets — declarative, so both frameworks
evaluate it identically rather than each writing its own predicate.

### 10.4 — The failure contract (the part that makes a UI portable)

This is the whole reason the phase exists. Both stacks must emit the same thing:

- **401 vs 403 is not a judgement call.** No credentials, or credentials that fail verification →
  **401** with a `WWW-Authenticate` challenge. Valid credentials that lack the required scope or role
  → **403** with no challenge. RFC 6750 §3 is unambiguous and both surveyed codebases would have had
  to guess.
- **`WWW-Authenticate` is constructed, not hand-written.** RFC 6750 §3 defines the syntax and the
  `error` codes (`invalid_request`, `invalid_token`, `insufficient_scope`); RFC 7617 defines the
  `Basic realm=...` form. Ship `challenge_header(...) -> str` building both, and test it against the
  RFC's own examples. A hand-assembled challenge string is how two services end up differing on a
  header a browser actually parses.
- **The problem body is the normal one.** `AuthenticationFailed` → 401 slug `unauthorized`,
  `PermissionDenied` → 403 slug `forbidden`, both already in `default_registry()` from §2.2. Nothing
  new on the wire beyond the header.
- **Never leak why verification failed.** The 401 `detail` says "authentication failed"; the reason
  (expired, bad signature, unknown `kid`) goes to the injected `log`. Same policy as the 5xx rule in
  §2.2, and for the same reason.

### 10.5 — What this phase does *not* unify

- **SAML flows.** SAML 2.0 terminates in an assertion and a session, not a bearer token; the
  redirect/POST binding, metadata and signature handling are the SP library's job and differ per
  framework (`python3-saml` under Django). **Web defines only the assertion→`Principal` mapping**;
  each package keeps its own flow. Trying to share the flow produces an abstraction neither side can
  use.
- **Login endpoints, token issuance, refresh, session cookies.** Application concerns, and pykit is
  not an authorization server.
- **Basic auth as a production mechanism.** Both framework packages ship basic auth (RFC 7617)
  because local development and simple internal deployments genuinely need it — and both must mark
  it as such in their docs and produce the identical 401 challenge.

> **Pending gap (2026-09-13, not yet a phase):** neither `rn-forge-web` nor `rn-forge-commons`
> ships a ready-made `Authenticator` that wires `JwtVerifier`/`JwksCache`/`discover_oidc` through
> `principal_from_claims` to a `Credentials → Principal` implementation. Every consuming app
> currently hand-writes this glue identically for its DRF `PrincipalBearerAuthentication` subclass
> and its FastAPI `bearer_auth()` authenticator. A single `OidcAuthenticator` (issuer/audience in,
> `Authenticator` out) belongs in this module or in commons, reused unchanged by both framework
> bindings — it stays inside the "verify + map claims" boundary this phase already draws and does
> not cross into login/token issuance. No phase number assigned; needs a decision before scoping.
> See [`docs/auth-overview.md`](../auth-overview.md) for the fuller writeup.

**Tests.** `tests/test_auth.py` (`unit`): `Principal` round-trips through `DataclassMixin`;
`Requirement` evaluation for each of the four set forms including the empty requirement; `authorize`
raises `PermissionDenied` and not `AuthenticationFailed` for a scope miss; `challenge_header` matches
RFC 6750 §3 and RFC 7617 examples verbatim; the 401 problem body carries no verification detail while
the injected `log` does.

---

## Phase 11 — `conformance/`: the table both frameworks are tested against

**This phase is the only thing in the package that can catch Django and FastAPI drifting apart.**
Every other test asserts one side against the primitives. Nothing today asserts that the two stacks
emit the *same JSON* for the same situation, so the first divergence surfaces in an application's
integration testing — or in a UI.

### 11.1 — Why it lives here, as data

It cannot live in `rn-forge-django` or `rn-forge-fastapi` (either one would need the other installed),
and it cannot import both into this package's tests — that breaks the boundary rule the whole package
rests on. So **this package ships the scenarios as framework-free data, and each framework package
ships a driver that runs its own stack through them.** The table is the specification; the drivers are
two independent proofs against it.

```python
@dataclass(frozen=True)
class ConformanceCase:
    id: str
    description: str
    request: RequestSpec          # method, path, headers, query, body
    expect_status: int
    expect_headers: Mapping[str, str]     # exact or predicate
    expect_body: Mapping[str, Any]        # exact, after correlation/instance redaction
```

`rn_forge.web.conformance.CASES` is a sequence of these, plus `redact(body)` which blanks the members
that legitimately differ per request (`instance`, the correlation extension, timestamps). A driver is
then about fifteen lines: build the app, issue the request, redact, assert.

### 11.2 — What the table must cover

One case per settled decision, because a decision with no case in this table is a decision that can
silently diverge:

| Area | Cases |
| --- | --- |
| Problem bodies | unregistered exception → 500 with no leaked detail; registered `DomainConflict` → 409; a framework-native 404; a validation error, asserting **both** frameworks produce the same RFC 6901 pointer list |
| Concurrency | absent `If-Match` on a required route → 428; mismatch → 412; `If-Match: *` → pass; malformed → 400 |
| Pagination | first page, continuation, last page (`nextPageToken` absent); `pageSize` above the cap clamped **not** rejected; a tampered `pageToken` → 400 |
| Idempotency | first call; replay returns the stored response; same key with a different body → 409 |
| Health | all pass → 200; required fail → 503; optional fail → 200 degraded |
| Auth | no credentials → 401 with the RFC 6750 challenge; bad scope → 403 with no challenge |
| Casing | every response body above is camelCase (§ the casing rule), asserted structurally rather than per-case |
| Correlation | inbound `X-Correlation-ID` echoed; absent one generated and present in both the header and the problem body |

### 11.3 — Rules

- **A case is added in the same change as the decision it encodes.** A phase that settles a status
  code and does not add its case has not finished.
- **The drivers assert equality to the table, never to each other's output.** Two stacks agreeing on
  the wrong thing is not conformance.
- **`redact` is the only place that knows what may legitimately vary.** If a driver needs its own
  redaction, the shape is not actually shared and that is the finding.
- The table ships in the package (not in `tests/`), because the framework packages import it. It is
  public API and it appears in the curated `__init__` under `conformance`.

**Tests here.** The table's own tests are trivial and still worth having: every `id` unique, every
case's `expect_body` survives `redact` idempotently, and the table is non-empty for each area above —
so deleting a section of coverage fails rather than passing quietly.

---

## The unification boundary — what this package will never contain

Recorded explicitly because the "deferred with a trigger" entries below could otherwise be read as
staging posts on the way to a unified ORM layer. **They are not.** Two things are permanently out of
scope, and a future phase proposing either needs to overturn this section first.

**A unified model base class or repository protocol.** Django's ORM is active-record with a
metaclass-driven declarative layer and a global app registry; SQLAlchemy is data-mapper with a unit of
work and explicit sessions. They differ on transaction boundaries, lazy loading, identity map, and
migration generation — which is to say on everything a shared base class would have to take a position
on. A shared *repository protocol* is worse than a shared base: it converges on a query API that is
the intersection of two ORMs, which is an API neither side's users will accept, and it acquires a new
method every time an application needs something the intersection lacks.

**A unified serializer abstraction.** A DRF `Serializer` is bidirectional — validation, ORM write
behaviour and `to_representation` in one object. A pydantic model is a parse-and-validate boundary.
There is no honest common supertype, and constructing one means reimplementing whichever framework's
half is missing.

**What *is* unified instead, and is enough:** the wire shapes (§2, §4, §6, §10), the field-name and
casing rules, the status codes, and — Phase 9.5 — the model *vocabulary*: column names, types and
semantics that each ORM's base class conforms to without sharing code. The single exception where a
protocol is justified is `Versioned` (a `pk` and an `int` `version`), because `check_precondition`
(§3.3) already takes exactly those two values and is the only point in this package that touches a
persisted object at all. Nothing beyond that.

---


## Amendments to plans already written

Executing this plan **requires** the following changes to the other two documents. Make them before
executing either, or they will conflict.

### A.1 — `django-upgrade-plan.md`

- **Phase 1** (conflict exceptions + problem-details handler): the exceptions and the body builder move here.
  That phase becomes *"a DRF `exception_handler` adapter over `rn_forge.web.problem`"* — roughly 30
  lines instead of a module. Its "put the exceptions in `rn_forge/django/exceptions.py`" decision is
  **reversed**: I argued that on the grounds that commons had no caller; this package is the caller
  that was missing.
- **Phase 1 status mapping**: `VersionConflict` maps to **412**, not 409. See §3.1.
- **Phase 3** (idempotency): becomes a Django-cache adapter implementing
  `rn_forge.web.IdempotencyStore`, gaining body-hash reuse detection it did not have. It must use
  `cache.add()` for the atomic claim — see §5.1.
- **Phase 4** (`enforce_version`): delegates to `check_precondition`; keeps only the body-key fallback
  and the DRF plumbing.
- **Phase 6.1** (readiness view): becomes a thin view factory over `run_checks_sync`.
- **Phase 7** (request-ID middleware): keeps the WSGI middleware and drops the ContextVar (imports it
  from `rn_forge.web.context`). Its default header name changes from `X-Request-ID` to
  **`X-Correlation-ID`**: that default existed only to preserve a cims call site, and cims is being
  rewritten. The name stays configurable for anyone fronted by infrastructure that stamps a different
  header.
- **Phase 9** (OIDC): unaffected by this plan, but see A.2 — it should consume a commons module.
- **Phase 10** (messaging): `MessageBus`/`InMemoryMessageBus`/`HandlerRegistry` move to **commons**,
  not here — messaging is not HTTP-shaped, and a worker needs it. See A.2.

**Four further amendments, added with Phases 10 and 11:**

- **Phase 2 (pagination) is re-scoped.** `StandardPagination(PageNumberPagination)` stops being the
  standard. Ship a `CursorPagination` over `rn_forge.web.pagination` emitting the AIP-158 envelope
  (§4.1) as the class an application reaches for by default; keep the page-number class, renamed to
  make its status obvious, as an explicitly **legacy** option for endpoints that genuinely need a
  total and a jumpable page index. Subclass DRF's own `CursorPagination` for its keyset machinery —
  which is proven and is the hard part — and override only the cursor codec and
  `get_paginated_response`/`get_paginated_response_schema`. Do not reimplement keyset SQL. The
  `reverse`-flag question in §4.3 is decided here and recorded.
- **Phase 9 (JWKS bearer auth) is re-scoped** to a binding: a DRF `BaseAuthentication` returning the
  `rn_forge.web.auth.Principal` (§10.2), over the commons verification module, with the 401/403 and
  `WWW-Authenticate` behaviour coming from §10.4 rather than from DRF's defaults — DRF's stock
  behaviour does not match RFC 6750 and must be overridden, not inherited. Basic auth (RFC 7617)
  ships alongside it, documented as local-development and simple-deployment only.
- **Phase 12 (drf-spectacular) is promoted from docs-only to shipped code.** Two things a recipe
  cannot deliver: the camelCase renderer/parser wired through the settings facade so the casing rule
  holds by default, and a DRF serializer mirror of `ProblemDetail` plus a spectacular postprocessing
  hook so the Django schema names the shared components identically to the FastAPI one and declares
  the error responses. Pin `OAS_VERSION` to 3.1.0.
- **A new phase: the conformance driver.** ~15 lines running the Django stack through
  `rn_forge.web.conformance.CASES` (§11). It is the only test in that package that can fail because
  of something FastAPI does.

### A.2 — `commons-upgrade-plan.md`

Three new modules, each justified by a consumer that exists today:

- **`secrets.py`** — a `SecretStore`/`AsyncSecretStore` protocol plus `EnvSecretStore`. intellibench's
  `SecretPort` (`libs/backend/ports/.../secrets.py`) is 15 lines and its `EnvSecretPort` docstring
  literally says "a managed-identity or key-vault-backed adapter replaces this one, not the port."
  The Azure plan's Phase 2 implements it. Commons, not web — a CLI or worker needs secrets too.
- **`messaging.py`** — `MessageBus` protocol + `InMemoryMessageBus`, moved out of the django plan's
  Phase 10 so `rn-forge-azure` can implement it without depending on Django.
- **`objects.py`** — an `ObjectStore` protocol (get/put/delete/exists over bytes), which is what the
  deferred claim-check pattern needs and what the Azure plan's Phase 3 implements.
- **`auth/` — token verification, and it is now a blocker rather than a suggestion.** The earlier
  note said only that OIDC/JWKS "belongs in commons". Phase 10 here depends on it concretely, so it
  needs a shape: JWKS fetch with caching and key rotation, JWT signature/claims validation
  (`pyjwt[crypto]` behind an extra), OIDC discovery via `/.well-known/openid-configuration`
  (RFC 8414), and a `verify(token) -> Mapping[str, Any]` returning verified claims. It returns
  claims, **not** a `Principal` — `Principal` is a wire-contract type and lives in web, and commons
  must not depend on web. The mapping from claims to `Principal` is web Phase 10's.

  > **Built (2026-09-12)** as `rn_forge/commons/integration/auth.py` (`auth` extra), with the default
  > claims → `Principal` mapping added here as `principal_from_claims`.

  Build order: this module, then web Phase 10, then the two framework bindings. Both the django plan's
  Phase 9 and the fastapi plan's deferred `Security` dependency are blocked on it.

### A.3 — `commons-upgrade-plan.md` Phase 8 (resilience) needs redesigning

This is the most consequential finding of the intellibench survey. That phase specifies `pybreaker` +
`tenacity` + sync `httpx`, taken from cims. intellibench independently built the same thing and could
not have used that design:

- **It is async.** `httpx.AsyncClient`, `tenacity.AsyncRetrying`, `async def send`. `pybreaker`'s
  model does not fit an async call path cleanly.
- **Breakers are per-key**, not per-client — one breaker per Azure DevOps organisation, held in a
  dict inside the client (`_circuit_breaker.py::CircuitBreaker._states`).
- **`clock` and `sleep` are injected** so tests run on a fake clock instead of real wall time. Any
  breaker without this has untestable timing behaviour.
- **It is `Retry-After`-aware.** `_client.py::_wait` prefers the response's `Retry-After` over
  exponential backoff, and `_rate_limit.py::parse_retry_after` handles both the delta-seconds and the
  HTTP-date forms.
- **It carries a token-bucket rate limiter** (`OrgRateLimiter`) that clamps itself from
  `X-RateLimit-Remaining` response headers — "never optimistic".

None of that is exotic; all of it is missing from the pybreaker-based design.

Recommendation, and note that the workspace principle changes the shape of it: **start from a library
search, not from intellibench's hand-rolled breaker.** That breaker is 91 lines of prior art proving
what the design must support (async call path, per-key state, injected `clock`/`sleep`,
`Retry-After` awareness) — it is a specification, not the implementation to copy. Concretely, commons
Phase 8 should:

1. Evaluate maintained async-capable circuit breakers before writing one. `pybreaker`'s model does not
   fit an async path cleanly, so it is likely out — but "hand-roll it" is a conclusion that has to be
   reached, not assumed.
2. Use a proven retry library rather than a bespoke loop: `tenacity` (`AsyncRetrying`) or
   [`stamina`](https://pypi.org/project/stamina/) (26.1.0), which is built on tenacity and has a much
   smaller, opinionated API — the better wrap target if it covers the `Retry-After` case.
3. Only hand-roll what the search genuinely does not cover (the token-bucket limiter clamping from
   `X-RateLimit-Remaining` is the likely candidate), and record the negative result.
4. Move `parse_retry_after` into commons alongside whatever wins — **commons, not `rn-forge-web`**.
   It is needed by outbound callers that never serve HTTP (`rn-forge-azure` among them), and commons
   cannot import web without inverting the dependency. The mirror-image concern, parsing an upstream
   `application/problem+json` body, does live in web — see §2.5 — and is written as a pure function
   over a mapping so no client library is pulled in either direction.

Treat that as its own decision with its own gate — it is not this plan's to make, but it is this
plan's to report.

---

## Deferred — do not build these yet

- **`rn-forge-fastapi` — no longer deferred; the trigger fired.** The condition was "the first FastAPI
  application rewritten on `rn-forge-web`", and there are now two: intellibuild
  (`python-web-api`, `framework = fastapi`) and kiln's own `golden/python-web-api`, which under
  ADR-0005 is authored *before* the app that copies it. The package is planned in
  [`fastapi-library-plan.md`](./fastapi-library-plan.md), which starts from the extraction candidates
  in the next section. It is still blocked on Phases 1-8 here, and Phase 9's `wiring-fastapi.md`
  remains the interim answer until it lands.
- **`rn-forge-sqlalchemy`.** intellibench's `storage/models/base.py` (declarative base, naming
  convention, `TimestampMixin`, `ScopedModel`) and `repository.py`'s optimistic-`update`/
  `StaleVersionError` are the SQLAlchemy counterpart of `rn_forge.django.models.base`. Genuinely
  reusable for the Alembic apps, and genuinely a separate package. Trigger: the first SQLAlchemy
  application rewritten on this kit — plan it with that app's spec, for the same reason as above.

  **Where it sits, since this is asked every time.** It is a **sibling of `rn-forge-django` and
  `rn-forge-fastapi`, not a layer under either**, and it depends on `rn-forge-web`:

  ```text
  commons ──► web ──► django
                └───► fastapi
                └───► sqlalchemy        (sibling; imports neither django nor fastapi)
  ```

  It needs web because three of its contents implement web protocols — the keyset predicate consumes
  `web.pagination.Cursor`, the optimistic-update helper raises `web.VersionConflict`, and the SQL
  idempotency store implements `web.AsyncIdempotencyStore`. It must **not** import `rn_forge.fastapi`:
  persistence is not HTTP, and a Celery worker or a CLI backfill using these models serves no
  requests. An import-linter contract states this in the same change that creates the package.

  **How each package relates to it:**

  | Package | Relationship |
  | --- | --- |
  | `rn-forge-commons` | Unaware of it, as of everything above it. |
  | `rn-forge-web` | Unaware of it. Web declares the protocols; this package implements some of them. |
  | `rn-forge-django` | **No relationship at all.** Django has its own ORM; nothing is shared but the Phase 9.5 model vocabulary, which is prose. |
  | `rn-forge-fastapi` | **No import in either direction.** An application depends on both and wires them together; that is the application's job, and it is why `rn-forge-fastapi` ships no store implementations. |

  **Likely contents**, recorded now so the eventual plan starts from a list rather than a survey:
  the declarative base and the Alembic constraint-naming convention (the classic `NAMING_CONVENTION`
  dict — small, and the thing every project gets wrong once); audit-column and `version` mixins
  conforming to `model-conventions.md`; the optimistic `update` helper; the `Cursor` → keyset
  predicate translation; an `AsyncIdempotencyStore` over `INSERT ... ON CONFLICT DO NOTHING`; session
  and unit-of-work helpers; and readiness checks returning `web.health.CheckResult` (connectivity,
  and "migrations at head"). Multi-tenant scoping stays deferred separately — see the next entry.

  **What it will not contain:** a repository base class generic over entity type, or anything shaped
  like a query abstraction. See "The unification boundary" above; that section binds this package too.
- **Multi-tenant row scoping.** `ProjectScopedRepository`, the `before_execute` isolation hook that
  rejects any `UPDATE`/`DELETE` without a `project_id` predicate, RLS session binding, and the
  exemption allowlist. This is the most impressive code in intellibench and the most opinionated —
  it encodes one specific tenancy model with sentinels for org- and system-scoped rows. Generalizing a
  tenancy model from a single application's assumptions is how a library acquires a shape nobody else
  can use; revisit when a second app's rewritten spec states its tenancy requirements.
- **An LLM port.** `intellibuild_ports/llm.py` + the Azure OpenAI adapter. See the Azure plan.

---

## FastAPI extraction candidates (for the future `rn-forge-fastapi` plan)

Recorded now, while the survey is fresh. Everything here is *thin* — which is the argument for
deferring the package, and the reason it will be quick when it happens.

**Worth extracting** (all from `apps/api/src/intellibuild_api/`):

- `handlers.py::register_exception_handlers(app)` — registers problem-details handlers for
  `StarletteHTTPException`, `RequestValidationError` and bare `Exception`. Becomes
  `register_problem_handlers(app, registry=...)` over `rn_forge.web.problem`. ~40 lines and it is the
  single highest-value FastAPI adapter.
- `handlers.py::_status_mapping` — the status-code→slug table for `HTTPException`s that carry no
  registered exception type. Folds into the default registry.
- `pagination.py::cursor_params(cap)` — a dependency factory returning the token and page size with
  the size clamped. ~10 lines over `rn_forge.web.pagination.clamp_page_size`. **Ships as
  `page_params` with AIP-158 parameter names** (§4.1); the inventory name here is intellibench's.
- `idempotency.py::require_idempotency_key` and `concurrency.py::require_if_match` — `Header(...)`
  dependencies raising the `rn_forge.web` exceptions. Five lines each.
- `app.py::_custom_openapi` — injects `ProblemDetail` into `components/schemas` even though no route
  declares it as a `response_model`, because the handlers build error bodies by hand and FastAPI's
  schema collection never sees them. **This is the non-obvious one** — without it, a generated
  TypeScript client has no error type at all.
- Pydantic mirrors of the `rn_forge.web` dataclasses (`ProblemDetail`, `Page[T]`) for use as
  `response_model`s.
- A `/healthz` + `/readyz` router factory over `rn_forge.web.health.run_checks`.

**Not worth extracting:** `app.py::create_app` (its shape — take a constructed `Settings` and
container, build nothing — is a *convention* worth documenting, not code worth shipping),
`ports_container.py` and `dependencies.py` (application-specific DI), every router, `models.py`,
`settings.py`.

---

## Final checklist before calling this done

- [x] `requires-python = ">=3.14"` on `rn-forge-web`; commons and django floors untouched
- [x] Phase 0.2's two library evaluations decided, with reasons, in the package README — including the
      negative results for Phases 3–6
- [x] `uv sync --all-extras && uv run pytest packages/rn-forge-web` green
- [x] Every module imports with the base install — there is no `asgi` extra and no extra-gated path,
      because Phase 0.2 rejected `asgi-correlation-id` (see "Implementation status")
- [x] `uv run pyright` clean across every package
- [x] `uv run ruff check . && uv run ruff format --check .` clean
- [x] The framework-boundary grep returns nothing — no `django`, `fastapi`, `starlette` or
      `rest_framework` import anywhere under `packages/rn-forge-web/src/`
- [x] `.importlinter` carries the `web-is-framework-free` and `web-layers` contracts and
      `uv run lint-imports` is green — the grep is the fast check, the contract is the gate
- [x] `rn_forge.web` imports neither `rn_forge.cli` nor `rn_forge.tooling` (same contract)
- [x] The commons dependency is a pinned direct URL at a release tag (kiln D46), and the installation
      guide documents that form rather than `uv add rn-forge-web`
- [x] The package is wired into pykit's repo shape per alignment §6: workspace members, sources, the
      `workspace` dependency group, `.importlinter`, root `mkdocs.yml` nav and `docs/index.md`.
      `[archetype.python-lib] packages` and the `state.json` re-seed are **not** done because
      `.rn-forge/` does not exist yet — alignment §6 says not to invent kiln files early. Redo those
      two after kiln Phase F.1 regenerates pykit's skeleton.
- [x] Every declared dependency is justified in `pyproject.toml` and in the README's
      "Dependencies and why" section; none of them is a web framework
- [x] Any wrapped library's exceptions are translated to `AppException` subclasses at the wrapper
      boundary — no third-party exception type reaches a consumer
- [x] `src/rn_forge/web/__init__.py` re-exports every public symbol, `__all__` sorted
- [x] `uv run --directory packages/rn-forge-web --group docs mkdocs build --strict` clean
- [x] Phase 9's context pack complete: `api-conventions.md`, both wiring guides, the checklist, and a
      runnable example per framework covered by a test
- [x] `api-conventions.md` names no application and assumes no domain, and carries the casing rule
      and the OpenAPI conventions as well as the seven modules' wire contracts
- [x] `model-conventions.md` shipped (Phase 9.5); it contains no code
- [x] Pagination is AIP-158 on the wire (`pageSize`/`pageToken`/`nextPageToken`), the page size is
      clamped and never rejected, and `totalSize` is off by default
- [x] Phase 10's `Principal`, protocols and `challenge_header` shipped; the 401/403 boundary follows
      RFC 6750 §3 and the 401 body leaks no verification reason
- [x] Phase 11's conformance table ships in the package (not in `tests/`), is re-exported from the
      curated `__init__`, and has at least one case per area in §11.2
- [x] Every wire decision settled in this plan has a conformance case; a decision with no case is
      treated as unfinished
- [x] The unification boundary section is present and the deferred entries below it do not read as
      staging posts toward a shared ORM layer
- [x] `CLAUDE.md`'s repository-overview section describes the new package and the dependency direction
      (`web → commons`, `django → web → commons`, `fastapi → web → commons`), and says that web
      imports neither `rn_forge.cli` nor `rn_forge.tooling`
- [x] The amendment sections above applied to the commons and django plans
- [x] Nothing committed or pushed — leave the working tree for review

## Not in this plan (deliberately deferred)

- **Any change to intellibench or cims.** Not because their call sites must be preserved — they are
  being rewritten — but because their rewrites are work in their own repositories, driven by their own
  specifications. What this plan owes them is Phase 9's context pack, not patches.
- **Lowering any package's Python floor.** No longer a prerequisite for anything here (Phase 0.1).
  Should a future consumer need it, it is a project-wide decision with its own gate.
- **The commons Phase 8 resilience redesign** (§A.3) — reported here, decided there.
