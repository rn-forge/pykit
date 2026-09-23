# pykit plans

The pykit plans and the retired workspace-wide standardization plan. This page is the **execution
order** and the **status board** — read it before picking up any plan, because several phases are
blocked on phases in other documents and none of the plans repeats the whole graph.

**Updated 2026-09-19.** Every original phase pykit can take on its own is implemented across the commons,
web, django and fastapi plans, and all of it up to 2026-09-13 is committed — commons Part F and that
day's gap pass landed in `757908e`. All three close-out items — the strict-dataclass flip (commons E.1a), the
OpenAPI naming rules (web §9.1) and `OidcAuthenticator` (web §10) — are in the working tree.
**The original pykit close-out list is complete.** The consumer reuse follow-up
below is newly planned and does not block the release. Golden repos in kiln are
downstream acceptance, not pykit work.
`rn-forge-azure` and `rn-forge-sqlalchemy` are **parked**.

The web, azure and django plans were drafted before `rn-forge/kiln` existed and each opens with an
**"Alignment with the standardization plan"** section stating what the workspace changed around them
(three library layers, pinned-git-tag releases, the D55 layout rule, import-linter contracts, and
which kiln archetype each consumer is). Read that section before the plan it heads.

**Implemented, 2026-09-18:** the
[standard FastAPI application layer](fastapi-app-layer-plan.md) adds the
standard `create_app` assembly. It is not a new release blocker. The completed
close-out work above remains historical.

**Planned, 2026-09-19:** the first application-layer adoption, plus a review of
three further in-progress FastAPI applications (IntelliBuild, Apollo,
PhotoTidy), identified six reusable pieces across `rn-forge-commons`,
`rn-forge-web` and `rn-forge-fastapi` — and six recurring patterns deliberately
left with their applications. See the
[web API consumer reuse plan](web-api-reuse-plan.md).

**Re-baselined, 2026-09-21:** a review of `rn-forge-web`, `rn-forge-fastapi` and
`rn-forge-django` against the question "does the kit follow standards, or does
it replace them?" set a new order of authority: published standard, then the
framework's native mechanism, then pykit. It found five wire deviations, the
wire types modelled three times over, and OpenAPI patching that existed only so
the two stacks' documents would read alike. See the
[standards re-baseline plan](standards-rebaseline-plan.md); it takes precedence
where older plans disagree. The Account Portal and IntelliBuild are **parked**
as acceptance consumers (both are work in progress). **R1 and R2 are
implemented (2026-09-21); R2.5 was implemented and committed on 2026-09-22
(`373d6bc`).** R3, R4, R5 and R10 are done as of 2026-09-23 (R3, R4 and R10
uncommitted; R5 is evaluation only). R6 is still open. On 2026-09-22, R7
(tabular transfer and bulk, adopting `tablib` and `django-import-export`) was
specified and R8 (AIP adoption) planned. R9 (SQLAlchemy and `tablib` across both
stacks) is open for ideation in a new session. See "What is open" below.

## The documents

| Document | Scope | Status |
| --- | --- | --- |
| [`commons-upgrade-plan.md`](./commons-upgrade-plan.md) | `rn-forge-commons` runtime foundation + the split of the development layer into `rn-forge-cli` and `rn-forge-tooling` | **Parts A–F committed; the strict-dataclass follow-ups done (E.1a, 2026-09-15); Part G, the `pydantic` extra, in the working tree (2026-09-16).** Open: D.8 release (last). D.9 and F3.3 are kiln acceptance |
| The standardization plan (retired; outside this repo) | Workspace-wide: the library layering, the kiln generator, the archetypes and golden repos, the rebuilds of agentkit and intellibuild | **Retired at revision 14** (2026-09-12), replaced by kiln's `docs/specs/` and `docs/adr/`. D-numbers resolve through kiln's `docs/plans/context.md` §2.2, phases through §2.1, and the pykit-side sections through [`kiln-dependencies.md`](./kiln-dependencies.md) |
| [`kiln-dependencies.md`](./kiln-dependencies.md) | What kiln needs from pykit: the lifecycle surface (kiln C.3), `rn-forge-fastapi` for kiln's web archetypes, and the release trigger | **Handoff, 2026-09-12; updated 2026-09-13.** Lifecycle surface done (commons Part F); fastapi implemented, its acceptance is kiln's; releases follow kiln's in-progress work |
| [`web-library-plan.md`](./web-library-plan.md) | `rn-forge-web` — framework-agnostic HTTP primitives | **All eleven phases implemented; committed at `8b5160b`**, plus §9.1 (the OpenAPI naming rules) and §10's `OidcAuthenticator` (both 2026-09-15). Open: the release tag |
| [`django-upgrade-plan.md`](./django-upgrade-plan.md) | `rn-forge-django` — adapters over web/commons + new Django-only modules | **All phases (0–13) implemented; committed at `9d8588c`**; the PostgreSQL suite was run locally on 2026-09-13. Open: the release tag, and `golden/python-web-app-django` (kiln) |
| [`fastapi-library-plan.md`](./fastapi-library-plan.md) | `rn-forge-fastapi` — FastAPI adapters over `rn-forge-web` | **Phases 0–7, 6b and 6c implemented; committed at `3e80dbd`.** Open: the `rn-forge-web` release tag, and Phase 8 (`golden/python-web-api`, kiln) |
| [`fastapi-app-layer-plan.md`](./fastapi-app-layer-plan.md) | Standard FastAPI app construction over the existing adapters | **Implemented (2026-09-18).** `AppConfig` and `create_app` |
| [`web-api-reuse-plan.md`](./web-api-reuse-plan.md) | What four FastAPI applications re-derive: `FastApiApp`, OpenAPI helpers, log redaction, SSE, problem extensions, correlation-ID validation and an opt-in CORS module | **Phases 0, 4 and 5 in the working tree; Phase 1 implemented, then withdrawn (2026-09-21)** by the re-baseline (R1). Phases 2, 3 and 6 planned. The Account Portal and IntelliBuild acceptances are parked |
| [`standards-rebaseline-plan.md`](./standards-rebaseline-plan.md) | Standards first: which parts of web, fastapi and django follow standards and native mechanisms, and which became a layer of their own | **R1 (OpenAPI accuracy only) and R2 (five standards deviations) implemented (2026-09-21).** **R2.5 (shared logic moved into web, plus the standard service surface: probes, api-catalog, deprecation, conditional GET, 429/503/413, security headers via `secure`, CORS, access log, idempotency runner, and a per-host deployment guide) implemented and committed (2026-09-22, `373d6bc`).** **R3 (W3C Trace Context through OpenTelemetry; `X-Correlation-ID` removed) implemented 2026-09-23, uncommitted.** **R4 (the shared wire types become pydantic models in web) implemented 2026-09-23, uncommitted.** R6 (django scope) is gated on the owner. **R7 (tabular transfer and bulk: `tablib` + `django-import-export` replace `drf/views/transfer.py`; a thin FastAPI equivalent; an AIP-136 `CustomMethodRouter` for DRF) ready to implement** (dependencies approved, router probed, 2026-09-22). **R8 (AIP adoption: `orderBy`, `validateOnly`, batch spellings, RFC 3339 time, path versioning, LRO shape) planned 2026-09-22.** **R9 (SQLAlchemy + `tablib` standardization across stacks) open for ideation**. **R10 (simplification pass after R3) implemented 2026-09-23, uncommitted, except R10.3 (Starlette's body limit), which was rejected at its probe.** **R5 (library evaluations) done 2026-09-23: all four exempt.** |
| [`cli-lifecycle-namespace-plan.md`](./cli-lifecycle-namespace-plan.md) | `rn-forge-cli` — an optional `namespace` for `[cli.lifecycle]`, so a tool can mount its verbs as `<tool> self …` | **Superseded (2026-09-21)** by `cli-lifecycle-retirement-plan.md`; the `namespace` design carries over into it unchanged |
| [`cli-lifecycle-retirement-plan.md`](./cli-lifecycle-retirement-plan.md) | Moves the whole `[cli.lifecycle]` mechanism out of `rn-forge-cli` into `rn-forge-tooling`, which now owns `LifecycleSurface` and `build_tool_app`; `rn-forge-cli` goes back to knowing only the generic `[cli]` shape | **Implemented (2026-09-21).** kiln's generator template updates in the same change (owner's tool) |
| [`azure-library-plan.md`](./azure-library-plan.md) | `rn-forge-azure` — Azure adapters for commons protocols | **Parked (2026-09-13).** Unblocked — the commons protocols it needs have landed — but not scheduled |

## Dependency direction

```
rn-forge-commons  ←  rn-forge-cli  ←  rn-forge-tooling  ←  agentkit / kiln
rn-forge-commons  ←  rn-forge-web  ←  rn-forge-django
rn-forge-commons  ←  rn-forge-web  ←  rn-forge-fastapi
rn-forge-commons  ←  rn-forge-azure                        (parked; not built)

rn-forge-tooling  ←  rn-forge-django[codegen]    (extra; only rn_forge.django.codegen)
rn-forge-tooling  ←  rn-forge-fastapi[codegen]   (extra; only rn_forge.fastapi.codegen)
```

**The development layer is two packages, not one** (kiln D52): `rn-forge-cli` is what any program with
a command line takes — including business batches — and `rn-forge-tooling` is what a program that
installs itself, owns files in someone else's repo or renders templates takes. Placement is decided by
what an API's *signature* contains, not by who calls it today.

`rn-forge-web` never imports a web framework. `rn-forge-azure` will depend on commons only — never on
web, django, cli or tooling. `rn-forge-django` and `rn-forge-fastapi` are **independent siblings**
above web: neither imports the other, and neither runtime surface imports cli, tooling, Typer or Jinja.
Framework code generators ship as a `[codegen]` extra of their runtime package, live in a `codegen`
subpackage the runtime never imports, register under the entry-point group `rn_forge.kiln.generators`,
and are installed only in development environments (kiln D37, D56). Both `codegen` subpackages are
empty; the fences exist.

**None of this is on trust.** `.importlinter` at the repo root states every rule above and
`uv run lint-imports` gates every other CI job. A new package adds its contract in the same change
that adds its dependency — a boundary that only passes locally is not a boundary.

**Releases are pinned git tags, not PyPI versions** (kiln D46). Every rn-forge dependency is declared
as `<name> @ git+https://github.com/rn-forge/pykit@<tag>#subdirectory=packages/<pkg>`; the
`[tool.uv.sources]` workspace override exists for local development only and does not survive into a
built wheel. The pins already name the tags they will get; none of those tags is cut yet.

## Execution order

Phases within a plan run in their own order unless noted. These are the **cross-plan** edges:

| Step | Do this | Blocked on | Status |
| --- | --- | --- | --- |
| 1 | ~~commons Part A (Phases 0–5)~~ | — | **Done** — Phase 6's gate failed and was abandoned; see the gates table |
| 2 | ~~commons Phase 7 (env guards)~~ | — | **Done** |
| 3 | ~~commons Phases **8b, 8c, 8d** (messaging / secrets / objects protocols)~~ | — | **Done** — `rn_forge/commons/integration/{messaging,secrets,objects}.py` |
| 4 | ~~web Phase 0 (scaffold + library evaluations)~~ | — | **Done (2026-09-11)** — both candidate libraries rejected; see the web plan's implementation status |
| 5 | ~~web Phases 1–8~~ | web Phase 0 | **Done (2026-09-11)** |
| 5a | ~~commons `auth/` (JWKS + JWT verify + OIDC discovery)~~ | — | **Done (2026-09-12)** — `rn_forge/commons/integration/auth.py`, `auth` extra |
| 5b | ~~web Phase 10 (the auth contract)~~ | step 5a | **Done** |
| 5c | ~~web Phase 11 (the conformance table)~~ | web Phases 1–6, 10 | **Done** — ships as data in `src/` |
| 6 | ~~web Phase 9 (consumer context pack)~~ | web Phases 1–8 | **Done** |
| 7 | azure Phases 0–3 | commons 8c, 8d | **Parked (2026-09-13)** — unblocked, not scheduled |
| 8 | ~~django Phases 0, 2, 5, 8, 9, 12~~ | commons Part A | **Done (2026-09-12)** |
| 9 | ~~django Phases 1, 3, 4, 6.1, 7~~ | web Phases 1–6 | **Done (2026-09-12)** |
| 10 | ~~django Phase 6.2~~ | commons Phase 7 | **Done** |
| 11 | ~~commons Phase 8 (resilience)~~ | — | **Done** — built async per web plan §A.3 (`purgatory` + `stamina`) |
| 12 | **Release `rn-forge-web`** (tag `rn-forge-web-v0.1.0`), with the commons → cli → tooling tags and then django/fastapi | web Phases 1–8 | **Open** — follows kiln's in-progress work. Until the tags exist, django and fastapi resolve only inside the workspace, which nothing local catches |
| 13 | ~~fastapi Phase 0~~ | step 12 | **Done** — the web pin was written before its tag exists |
| 14 | ~~fastapi Phases 1–7 and 6b~~ | fastapi Phase 0 | **Done (2026-09-12)** |
| 14a | ~~django Phase 13 and fastapi Phase 6c (the two conformance drivers)~~ | step 5c | **Done** — both run every case in `CASES` with no skips |
| 15 | fastapi **Phase 8** (`golden/python-web-api` wires it end to end) | fastapi Phase 7, kiln Phase E | **Open** — kiln work; follows kiln's in-progress work |

**Every step pykit can take alone is done.** Step 12 is a release; step 15, commons D.9, kiln F3.3
(the lifecycle golden) and `golden/python-web-app-django` are golden repos in kiln. The owner has
sequenced all of them after kiln's in-progress work.

## Gated decisions

A gated phase needs a human decision, not an implementer's judgement. Every gate is resolved except
azure's two, which are parked with the package:

| Gate | Outcome |
| --- | --- |
| ~~commons Phase 6~~ | **Resolved (2026-09-07): gate failed, abandoned.** Replacing the `config.py` resolver with OmegaConf was estimated at 100-160+ lines of glue against an ~80-line threshold. Hand-rolled resolver unchanged. |
| ~~commons Phase 9~~ | **Resolved (2026-09-07): gate passed, built.** `StructLogger`, at `src/rn_forge/commons/logging/structlog.py`. |
| ~~django Phase 10~~ | **Resolved (2026-09-12): built, on the owner's decision.** Consumer: the cims successor; PostgreSQL CI job `django-postgres`; envelopes stay consumer-supplied |
| ~~django Phase 11~~ | **Resolved (2026-09-12): built, on the owner's decision.** `rn_forge.django.celery`, `celery` extra |
| ~~django Phase 2 / web §4.3~~ | **Resolved (2026-09-12): forward-only on both stacks.** No `reverse` on the web `Cursor`, no `previousPageToken` |
| ~~fastapi Phase 0.2~~ | **Resolved (2026-09-12): `rn_forge.fastapi` kept.** Reasons in the package README; a test asserts the disjoint `__path__` |
| ~~fastapi Phase 5~~ | **Resolved (2026-09-12): no module shipped.** Web's `CorrelationIdMiddleware` installs unchanged |
| azure Phase 4 | Service Bus `MessageBus` adapter? — **parked with the package** (django Phase 10, which it waited on, was built) |
| azure Phase 5 | OpenTelemetry export to Azure Monitor? — **parked with the package** |

**Commons Phase 18.4 is resolved:** use `rn-forge-tooling` for shared installer mechanics — now
`rn_forge.tooling.install` and its lifecycle verbs (commons Part F). Product coordinates and product
policy stay in agentkit and kiln. Do not create `rn-forge-selfkit`.

## What is open

### Standards re-baseline (first)

[`standards-rebaseline-plan.md`](./standards-rebaseline-plan.md):

- **R1 and R2 are implemented (2026-09-21).** R1 reduces the FastAPI OpenAPI
  repair to a `FastApiApp.openapi()` override (`repair_problem_schema`) that
  only declares problem responses, withdraws reuse Phase 1
  (`install_component_schemas`, `openapi_json`, `AppConfig.components`) and the
  `Page<Item>`/generic-name renaming on both stacks, and gives Django the same
  problem-response repair through a drf-spectacular postprocessing hook
  (`problem_responses_hook`). R2 fixes the idempotency statuses (422 for a
  mismatched body via a new `IdempotencyKeyInFlight` exception for 409 while
  the original is in flight), renames `errors[].message` to `errors[].detail`,
  and makes `about:blank` titles the HTTP status phrase. `api-conventions.md`
  §2, §5 and §9 are rewritten to match; both conformance drivers run every
  case with no skips; `uv run pytest`, `ruff check`, `ruff format --check`,
  `pyright` and `lint-imports` are all green. Full notes, including the two
  implementation judgment calls (the repair function's naming and Django's
  still-necessary `OPENAPI_VERSION` pin), are in the plan's R1/R2 sections.
- **R2.5 is implemented and committed (2026-09-22, `373d6bc`).** Part A moved
  the duplicated logic into `rn-forge-web`. Part B added the standard service
  surface on both stacks:
  - `/livez`, `/readyz` and a deprecated `/healthz`, with a 2 s check timeout;
  - RFC 9727 `/.well-known/api-catalog`;
  - RFC 9745/8594 deprecation headers;
  - `If-None-Match` → 304;
  - 429/503 with `Retry-After`, and 413;
  - the OWASP security headers, through the `secure` library;
  - CORS with the kit's exposed headers;
  - one access-log event in OTel names (deleted by R10.2);
  - a framework-free idempotency runner;
  - `deployment.md`, which maps the probes onto each host.

  The deviations from the spec are in the plan's "Part B implementation
  notes".
- **R3 is implemented (2026-09-23).** `X-Correlation-ID` is removed outright
  and replaced by W3C Trace Context through OpenTelemetry: `traceparent` in,
  `traceresponse` out, and a `trace_id` problem extension read from the
  active span. `rn_forge.web.context` is now `rn_forge.web.tracing`;
  `CorrelationIdMiddleware` is `AccessLogMiddleware` on both ASGI and Django,
  carrying no header handling. `FastApiApp` instruments itself by default
  (`AppConfig.tracing`); Django gets a new `rn_forge.django.tracing.instrument()`
  (the `otel` extra), called once before Django loads. New dependencies:
  `opentelemetry-api` (base, web), `opentelemetry-instrumentation-fastapi`
  (base, fastapi), `opentelemetry-instrumentation-django` (django's `otel`
  extra, verified not pulled in by `drf`). web-api-reuse Phase 5 is withdrawn.
  Landed ahead of R4 in the handoff order — see the plan's R3 section for why
  that was safe here. All validation green at the repo root.
- **R10 is implemented (2026-09-23, uncommitted), except R10.3.** A
  simplification pass after R3, under the standing rule "adopted first".
  R10.1 fixed R3's docs (`mkdocs build --strict` passes in web, fastapi and
  django). R10.2 deleted the access-log middleware on both stacks, along with
  `request_log_fields`, Django's `rn_forge.django.middleware` and api-conventions
  §17; `AppConfig.log` remains, for `problem.server_error` only. R10.4 moved the
  structlog trace processor to `rn_forge.commons.logging.structlog.otel_processor`.
  R10.5 renamed the problem member `trace_id` to `traceId` and deleted
  `SPAN_ID_KEY`. **R10.3 stopped at its probe:** Starlette 1.6's
  `RequestBodyLimitMiddleware` answers a declared oversized `Content-Length`
  with a plain-text 413 that replaces the app's response, so the kit's
  problem body is lost. The kit's `BodySizeLimitMiddleware` and
  `rn_forge.web.asgi` stay. The plan's "R10 status" section has the detail.
- **The conformance flake is fixed (2026-09-23).** `tracing.*` and
  `cors.exposed-headers-are-comma-joined` failed in roughly one full run in ten,
  on Django and on web's ASGI example, because
  `rn-forge-django/tests/test_tracing.py` reset the process-global response
  propagator to `None` instead of restoring it. Seed `1707347094` reproduced it;
  25 full runs pass after the fix.
- **Next session, in order:** R7 (ready); R6 and R9 need the owner. Releases still follow kiln's work.
- **R4** is implemented and complete (2026-09-23), uncommitted; nothing left
  in its scope.
  `ProblemDetail`, `Page`, `CheckResult` and `HealthReport`
  become pydantic models in `rn-forge-web`, deleting the FastAPI mirrors and
  the DRF wire serializers. It was verified against drf-spectacular's pydantic
  extension and is wire-neutral.
- **Owner decision:** R6 (the rest of django's non-API scope: SAML, Celery,
  fixtures and messaging; transfer is settled by R7).
- **R5 is done (2026-09-23): all four evaluations exempt.** `fastapi-problem`,
  `fastapi-pagination`, `drf-standardized-errors` and `django-health-check`
  each fail `api-conventions.md` without replacing their own machinery, so no
  dependency was added and no kit code deleted. Verdicts and revisit triggers
  are in the plan's R5 section. The module-docstring exemptions are written.
- **R7 (planned 2026-09-22)** replaces the ~2,200-line `drf/views/` transfer
  and bulk code with `django-import-export` `Resource`s over `tablib`, gives
  FastAPI a thin equivalent (`tablib` + pydantic, persistence left to the
  application), and moves both stacks to one standard wire: `GET` with `Accept`
  for export, `:import`, `:batchCreate`, `:batchDelete`, and RFC 9457 row
  errors. Requirements come from `ew-loop-api`, the reference consumer.
  Dependencies approved 2026-09-22. DRF's stock router cannot spell
  `:action` (and lets `/orders/12:cancel` reach `retrieve`); a probed
  route-table override, `CustomMethodRouter`, fixes both. It also settles the
  transfer half of R6.
- **R8 (planned 2026-09-22)** adopts the AIPs that fill gaps no RFC covers:
  132 `orderBy` (the one code item), 163, 231/234, 142, 185, 180, and 151's
  shape. It rejects the AIPs an RFC already governs (193, 154, 155, 134).
  **Owner decisions:** AIP-148 standard field names (`createTime` over
  `createdAt`, only cheap before the release tags) and AIP-164 soft delete.
- **R7 open questions:**
  - Is all or nothing the default when an import fails? `ew-loop-api` does
    partial saves today.
  - Which status does an export over the row cap return? `422` is
    recommended.
- **R9 (open, next session)** works out how SQLAlchemy and `tablib` can make
  transfer and persistence uniform across Django and FastAPI:
  - whether to unpark `rn-forge-sqlalchemy`;
  - one upsert contract over Django's `bulk_create(update_conflicts=True)` and
    SQLAlchemy's `on_conflict_do_update`;
  - one column spec, or two native idioms;
  - async;
  - keyset pagination with `orderBy`;
  - audit fields.

  Seven questions and their inputs are listed in the plan. Start there.

The rest of it (R3–R9) lands before the release tags.

### Web API consumer reuse

Implement the six independent phases in
[`web-api-reuse-plan.md`](./web-api-reuse-plan.md): composable OpenAPI helpers
and a CORS policy in `rn-forge-fastapi`; exception-carried problem extensions,
the unmapped-exception audit, correlation-ID validation and the SSE frame
contract in `rn-forge-web` (with its FastAPI adapter); structured-log redaction
in `rn-forge-commons.logging`. **Phase 0 is done:** `create_app` is now
`FastApiApp`, a `FastAPI` subclass, for consistency with `rn-forge-cli`'s
`CliApp` (owner's decision, 2026-09-19; the factory was removed, not kept
beside it). **Phase 1 is withdrawn (2026-09-21):** it was implemented on
2026-09-20 and is removed by re-baseline R1, because its only evidence came
from the two parked applications. Phases 4 and 5 are in the working tree. SSE is taken as a
thin wrapper over `sse-starlette`, evaluated and
functionally probed on 2026-09-19; log redaction is hand-rolled because no
maintained candidate fits; CORS ships as an opt-in module whose default is to
install nothing. Each phase names the application that accepts it by deleting
its local copy. None of this blocks the release.

### pykit close-out, in order

1. ~~**Strict dataclasses by default**~~ — **done 2026-09-15** (commons E.1a). `DataclassMixin`
   type-checks and raises `AppException`; `StrictDataclassMixin` is gone and
   `LenientDataclassMixin` is the opt-out; `Area`, `StateEntry` and the `FixtureDefinition` family
   are parsed through it. The pass found that dacite cannot type-check a PEP 695 `type` alias or an
   unbound type variable, so `Finding`, `CheckResult`, `HealthReport` and `Page[T]` opt out with
   their reason in the docstring — see E.1a.
2. ~~**Schema naming: `operationId` and the paginated component**~~ — **done 2026-09-15** (web §9.1).
   Both rules moved into a new `rn_forge/web/openapi.py` that the two bindings call, so there is one
   copy rather than two that agree until someone edits one: the paginated envelope is `Page<Item>`
   (a generic cannot be one component — OpenAPI has no generics), and an operation outside the six
   CRUD verbs is an AIP-136 custom method, `/orders/{orderId}:cancel` → `ordersCancel`.
   `api-conventions.md` §9 is rewritten to match, and a test on each stack proves they agree.
3. ~~**`OidcAuthenticator`**~~ — **done 2026-09-15** (web §10). Built as
   `rn_forge.web.oidc.OidcAuthenticator`, behind web's new `auth` extra and excluded from the
   curated `__init__.py`. It lives in web because its signature is `Credentials` in and
   `Principal` out — both web types, and commons cannot depend on web. Django's
   `JWKSAuthenticator` was moved into it rather than aliased, so `JWKSBearerAuthentication` and
   FastAPI's `bearer_auth()` now share one implementation; a test on each stack drives the same
   token through it. **Nothing pykit-side is left before the release.**
4. ~~**Strict pydantic models as a commons extra**~~ — **done in the working tree 2026-09-16**
   (commons Part G), for kiln F4.2. `rn_forge.commons.lang.models` behind the `pydantic` extra:
   `StrictModel` and `ModelValidationError`, which names every failing key by dotted path. The base
   package still takes no pydantic dependency, and a test proves the facade never loads it.

### Last: the release

**In plain terms:** today every package asks for its siblings by a version label (a git tag such as
`rn-forge-web-v0.1.0`) that has not been created yet. Inside this repository that does not matter,
because `uv` links the packages to each other directly. Anyone *outside* it — kiln, a golden repo, an
application — cannot install them until the labels exist. Cutting the release means merging this
branch to `main` and creating those tags, in dependency order: commons `v0.5.0` → cli `v0.1.0` →
tooling `v0.2.0` → web `v0.1.0` → django `v0.3.0` / fastapi `v0.1.0`. Nothing in the code changes
when that happens; the pins already name the tags. It is last so that everything above lands in the
first published version instead of forcing a second one. Creating a tag pushes, so it needs the
owner's word.

### Downstream acceptance — kiln's work, not a pykit item

pykit's packages are finished when the items above are. kiln then proves them in its golden repos
(kiln ADR-0005: a claim not shown in a runnable golden repo is not shown): `golden/python-app`
(commons D.9), `golden/python-tool` with `[lifecycle]` (kiln F3.3, `rn-forge-tooling`'s
`build_tool_app`), `golden/python-web-api`
(fastapi Phase 8) and `golden/python-web-app-django`, plus kiln's pin flip and `state.json` re-seed.
They are listed here only because a golden repo can surface a gap — and a gap it finds comes back as
a new pykit item, not as a reason to hold pykit open now.

**Waiting on kiln:** the `[codegen]` extras of `rn-forge-django` and `rn-forge-fastapi` (kiln D2), and
the `[archetype.python-lib] packages` entry plus `state.json` re-seed (kiln Phase F.1). The import
fences exist; the generators and kiln files do not.

**Parked (2026-09-13), not scheduled:**

- **`rn-forge-azure`** — [`azure-library-plan.md`](./azure-library-plan.md) is complete and unblocked;
  its Phase 4/5 gates and namespace decision are made when it is picked up.
- **`rn-forge-sqlalchemy`** — no plan yet; its likely contents are recorded in the web plan's
  "Deferred" section. Its trigger is unchanged (the first SQLAlchemy application rewritten on this
  kit — intellibuild), and it is planned with that application's spec, not ahead of it.
  **Revisit, 2026-09-22:** the owner wants to reconsider it as part of R9
  (standards-rebaseline-plan), because R7 leaves FastAPI's transfer
  persistence to each application until a SQLAlchemy package exists.
- **Multi-tenant row scoping** stays deferred until a second application states its tenancy model.

## Standing rules for every plan

- The workspace **design principles** (README / CLAUDE.md) bind all of these: don't reimplement a
  proven library; wrap it thinly for one design language; keep package boundaries; pykit is upstream.
- **Adopted first** (2026-09-23). When a library or the framework is adopted for a concern,
  everything it already emits or enforces is deleted from the kit, including code that predates
  the adoption. A conformance case only the deleted code satisfied is re-pointed or dropped, with
  the reason recorded in the plan.
- **Wire conventions come from published standards where one exists, not from house taste.** Settled
  and normative for both framework packages: RFC 9457 for errors, RFC 9110/6585 for preconditions
  (412/428), [AIP-158](https://google.aip.dev/158) for pagination (`pageSize`/`pageToken`/
  `nextPageToken`, clamped never rejected), RFC 8288 for the additive `Link` header, RFC 6750/7617 and
  OIDC for auth, OpenAPI **3.1.0** for schemas, and camelCase on the wire with `snake_case` in Python
  (Google JSON Style Guide / Microsoft REST Guidelines / proto3 JSON mapping). They live in web Phase
  9.1's `api-conventions.md`; a package that needs to deviate raises it there rather than locally.
- **Authority runs standard → framework-native mechanism → pykit** (re-baseline, 2026-09-21). pykit
  never owns a wire shape a standard already defines, and a maintained library that implements the
  standard is adopted rather than rejected for "deciding the wire shape". A consumer must not be able
  to tell *from the wire* whether an API was built with pykit, with the native libraries, or on
  another stack.
- **Django and FastAPI are held to the same *wire behaviour* by a shared test, not by review.**
  `rn-forge-web` ships the scenario table (Phase 11) as framework-free data; each framework package
  drives its own stack through it. A decision with no case in that table is a decision that will
  drift. **The OpenAPI document's text (component names, nullability spelling, enum hoisting) is
  not held identical:** each generator's native output stands, repaired only for accuracy. So a
  client generated from either document shares method names (`operationId`) and declared problem
  responses, but not type names or model structure. If an API
  ever has to be portable across stacks behind an unchanged client, that is a spec-first contract
  test, not generator post-processing.
- **A unified model base class, repository protocol or serializer abstraction is permanently out of
  scope** — see the web plan's "The unification boundary". What is shared is vocabulary
  (`model-conventions.md`) and wire shapes. The parked `rn-forge-sqlalchemy` is a **sibling** of the
  two framework packages, not a step toward merging them.
- **cims and intellibench are prior art, not compatibility constraints.** Both are being respecified
  and reimplemented against these libraries. Where a survey found a weaker design, the plans fix it.
- The Python floor stays **`>=3.14`** across the workspace.
- Every phase ends with its own validation command block, and every one of them includes
  `uv run lint-imports`. After standardization plan Phase F.1 regenerates pykit's skeleton, `task
  validate` is what CI runs and the `uv run …` forms are its inner primitives.
- **Adding a package is a repo-shape change.** pykit is the `python-lib` archetype (kiln D53):
  beyond the workspace members/sources/dependency group, a new package goes into
  `[archetype.python-lib] packages` in `.rn-forge/kiln/config.toml` (it drives the generated CI
  matrix, build and release jobs), needs a `.rn-forge/kiln/state.json` re-seed via `kiln apply`, and
  joins the root `mkdocs.yml` nav and `docs/index.md`. Those kiln files do not exist before Phase
  F.1 — do not create them early.
- **Consumers are archetypes, and a claim needs a golden repo.** intellibuild is `python-web-app`
  (`framework = fastapi`, `frontend = angular`, with a separately built frontend package — owner
  decision 2026-09-12; a standalone kiln plan that gates no release); the cims successor is
  `python-web-app` (`framework = django`). Under kiln ADR-0005 a claim not demonstrated in a runnable
  golden repo is not demonstrated — the rule that caught standardization Phase C shipping ADR-0009
  without evidence.
- Nothing is committed or pushed without the owner asking.
