# pykit plans

Six pykit documents plus the workspace-wide standardization plan. This page is the **execution
order** — read it before picking up any plan, because several phases are blocked on phases in other
documents and none of the plans repeats the whole graph.

**Updated 2026-09-10 for kiln revision 9.** The commons plan is implemented through Part D.7; the
web, azure and django plans were drafted before `rn-forge/kiln` existed and each now opens with an
**"Alignment with the standardization plan"** section stating what the workspace changed around them
(three library layers, pinned-git-tag releases, the D55 layout rule, import-linter contracts, and
which kiln archetype each consumer is). Read that section before the plan it heads. The fastapi plan
is new and is written aligned. No module design changed.

## The documents

| Document | Scope | Status |
| --- | --- | --- |
| [`commons-upgrade-plan.md`](./commons-upgrade-plan.md) | `rn-forge-commons` runtime foundation + the split of the development layer into `rn-forge-cli` and `rn-forge-tooling` | **Parts A–C committed; Part D.1–D.7 applied in the working tree.** D.8 (cut the three release tags) and D.9 (the `golden/python-app` acceptance) are open and need a decision to commit and push |
| `rn-forge/kiln/docs/plans/standardization-plan.md` (outside this repo; a pointer remains at `rn-forge/STANDARDIZATION-PLAN.md`) | Workspace-wide: the library layering, the kiln generator, the archetypes and golden repos, the rebuilds of agentkit and intellibuild | **Frozen at revision 14** (2026-09-12) and superseded by kiln's `docs/specs/` and `docs/adr/`. Its section references in the plans below still resolve |
| [`kiln-dependencies.md`](./kiln-dependencies.md) | What kiln needs from pykit: the lifecycle surface (kiln C.3), `rn-forge-fastapi` for kiln's web archetypes, and the release trigger | **Handoff, 2026-09-12** — the lifecycle surface is not started and blocks kiln release-1 |
| [`web-library-plan.md`](./web-library-plan.md) | **New** `rn-forge-web` package — framework-agnostic HTTP primitives | Ready; aligned 2026-09-10 |
| [`django-upgrade-plan.md`](./django-upgrade-plan.md) | `rn-forge-django` — adapters over web/commons + new Django-only modules | **All phases (0–13) applied in the working tree (2026-09-12)**, with the commons `auth` module they needed. Open: the release tags, and `golden/python-web-app-django` (kiln) |
| [`fastapi-library-plan.md`](./fastapi-library-plan.md) | **New** `rn-forge-fastapi` package — FastAPI adapters over `rn-forge-web` | **Phases 0–7 and 6c applied in the working tree (2026-09-12).** Open: the `rn-forge-web` release tag, Phase 8 (`golden/python-web-api` does not exist yet), and the django conformance driver it lands with (step 14a) |
| [`azure-library-plan.md`](./azure-library-plan.md) | **New** `rn-forge-azure` package — Azure adapters for commons protocols | Ready; aligned 2026-09-10 |
| [`01-extraction-from-cims.md`](./01-extraction-from-cims.md) | The original cims survey | **Superseded — background only** |

`01-extraction-from-cims.md` is the survey the others grew out of. Its recommendations have been
split, re-decided and in places reversed by the newer plans. **Do not implement from it.** Read it
only to understand where something came from.

## Dependency direction

```
rn-forge-commons  ←  rn-forge-cli  ←  rn-forge-tooling  ←  agentkit / kiln
rn-forge-commons  ←  rn-forge-web  ←  rn-forge-django
rn-forge-commons  ←  rn-forge-web  ←  rn-forge-fastapi
rn-forge-commons  ←  rn-forge-azure

rn-forge-tooling  ←  rn-forge-django[codegen]    (extra; only rn_forge.django.codegen)
rn-forge-tooling  ←  rn-forge-fastapi[codegen]   (extra; only rn_forge.fastapi.codegen)
```

**The development layer is two packages, not one** (kiln D52): `rn-forge-cli` is what any program with
a command line takes — including business batches — and `rn-forge-tooling` is what a program that
installs itself, owns files in someone else's repo or renders templates takes. Placement is decided by
what an API's *signature* contains, not by who calls it today.

`rn-forge-web` never imports a web framework. `rn-forge-azure` depends on commons only — never on web,
django, cli or tooling. `rn-forge-django` and `rn-forge-fastapi` are **independent siblings** above
web: neither imports the other, and neither runtime surface imports cli, tooling, Typer or Jinja.
Framework code generators ship as a `[codegen]` extra of their runtime package, live in a `codegen`
subpackage the runtime never imports, register under the entry-point group `rn_forge.kiln.generators`,
and are installed only in development environments (kiln D37, D56).

**None of this is on trust.** `.importlinter` at the repo root states every rule above and
`uv run lint-imports` gates every other CI job. A new package adds its contract in the same change
that adds its dependency — a boundary that only passes locally is not a boundary.

**Releases are pinned git tags, not PyPI versions** (kiln D46). Every rn-forge dependency is declared
as `<name> @ git+https://github.com/rn-forge/pykit@<tag>#subdirectory=packages/<pkg>`; the
`[tool.uv.sources]` workspace override exists for local development only and does not survive into a
built wheel. Each plan's scaffold section carries the corrected form.

## Execution order

Phases within a plan run in their own order unless noted. These are the **cross-plan** edges:

| Step | Do this | Blocked on | Why |
| --- | --- | --- | --- |
| 1 | ~~commons Part A (Phases 0–5)~~ | — | **Done** — Phase 6's gate failed and was abandoned; see the gates table |
| 2 | ~~commons Phase 7 (env guards)~~ | — | **Done** — django Phase 6.2 is unblocked |
| 3 | ~~commons Phases **8b, 8c, 8d** (messaging / secrets / objects protocols)~~ | — | **Done** — now `rn_forge/commons/integration/{messaging,secrets,objects}.py`, exported from the facade. This unblocked azure Phases 2–4 and django Phase 10 |
| 4 | **web Phase 0** (scaffold + library evaluations) | — | Blocking; decides what Phases 1/2/7 contain |
| 5 | web Phases 1–8 | web Phase 0 | In order; Phase 8 is the curated API + docs. **Add each Phase 11 conformance case in the same change as the phase that settles its decision** |
| 5a | ~~**commons `auth/`** (JWKS + JWT verify + OIDC discovery)~~ | — | **Done (2026-09-12)** — `rn_forge/commons/integration/auth.py`, `auth` extra. Returns verified claims; `rn_forge.web.principal_from_claims` maps them. Django binds it in `auth/drf/oidc.py`; fastapi can pass the same verifier behind a `web.Authenticator` |
| 5b | **web Phase 10** (the auth contract) | step 5a | `Principal`, the protocols, the 401/403 boundary and the RFC 6750 challenge. Must land **before** web Phase 8, whose curated `__init__` exports it |
| 5c | **web Phase 11** (the conformance table) | web Phases 1–6, 10 | Ships as data in `src/`, not in `tests/`. Both framework drivers import it |
| 6 | web **Phase 9** (consumer context pack) | web Phases 1–8 | The hand-off artifact for application specs |
| 7 | azure Phases 0–3 | commons 8c, 8d | Key Vault needs `SecretStore`; Blob needs `ObjectStore` |
| 8 | django Phases 0, 2, 5, 8, 9, 12 | commons Part A | Independent of the web package |
| 9 | django Phases 1, 3, 4, 6.1, 7 | web Phases 1–6 | All five are adapters over `rn_forge.web` |
| 10 | django Phase 6.2 | commons Phase 7 | Thin wrapper over `Environment.require` |
| 11 | ~~commons Phase 8 (resilience)~~ | — | **Done** — built async per web plan §A.3 (`purgatory` + `stamina`), not the original sync spec |
| 12 | **Release `rn-forge-web`** (tag `rn-forge-web-v0.1.0`) | web Phases 1–8 | kiln D46: django and fastapi declare it as a pinned direct URL, so the tag must exist before either can declare the dependency. A workspace override hides this locally, which is the trap |
| 13 | fastapi Phase 0 | step 12 | Blocking; the release, the namespace decision and the import contract |
| 14 | fastapi Phases 1–7 | fastapi Phase 0 | 1–6 are independent of each other except 3, which needs 1 and 2; 7 is the curated API + docs |
| 14a | **django Phase 13 and fastapi Phase 6c** (the two conformance drivers) | step 5c, and each package's own phases | **Land them together.** Each asserts its stack against the shared table; one alone proves nothing about drift, which is the only thing they exist to catch |
| 15 | fastapi **Phase 8** (`golden/python-web-api` wires it end to end) | fastapi Phase 7, kiln Phase E | The acceptance. It can fail the web/fastapi split rather than the code — read the phase before assuming it is a formality |

**Steps 1–3 and step 11 are done** (commons Parts A–C, committed at `4624bfe` plus the Part D work
in the tree). The live front of the graph is step 4 — web Phase 0 — and everything downstream of it.

**The development-layer
split is not a step here** — it is standardization plan Phase C/C.2, whose pykit half is applied in
the working tree: `rn-forge-cli` owns the Typer app factory, console, standard options and exit
codes; `rn-forge-tooling` owns state, templates, the generation engine, installer mechanics and the
docs checkers; commons kept `DirectoryLock`, `atomic_symlink` and `ManagedBlock`. What remains is
commons plan **D.8** (cut the commons → cli → tooling release tags, which means committing and
pushing) and **D.9** (the `golden/python-app` acceptance, which lives in the kiln repo).

Two steps are the ones most likely to be started too early. **Step 9** — five django phases will
silently reimplement the web package if its phases have not landed. **Step 12** — skipping the web
release tag leaves django and fastapi resolvable only inside the workspace, which nothing local will
catch.

## Decisions needed before implementation starts

Six phases are **gated** and need a human decision, not an implementer's judgement. An agent that
reaches one should stop and record the question, not guess:

| Gate | Question |
| --- | --- |
| ~~commons Phase 6~~ | **Resolved (2026-09-07): gate failed, abandoned.** Replacing the `config.py` resolver with OmegaConf was estimated at 100-160+ lines of pre/post glue against an ~80-line threshold — see the outcome note in the plan. Hand-rolled resolver unchanged. |
| ~~commons Phase 9~~ | **Resolved (2026-09-07): gate passed, built.** `StructLogger`, now at `src/rn_forge/commons/logging/structlog.py` after the D55 re-layout — see the outcome note in the plan for the four validated conditions. |
| ~~django Phase 10~~ | **Resolved (2026-09-12): built, on the owner's decision.** Consumer: the cims successor (`golden/python-web-app-django`); PostgreSQL CI job `django-postgres` added; envelopes stay consumer-supplied |
| ~~django Phase 11~~ | **Resolved (2026-09-12): built, on the owner's decision.** `rn_forge.django.celery`, `celery` extra; no relay-task wrapper |
| azure Phase 4 | Service Bus `MessageBus` adapter? Depends on django Phase 10's outcome |
| azure Phase 5 | OpenTelemetry export to Azure Monitor? |
| fastapi Phase 0.2 | Keep `rn_forge.fastapi`, or fall back to `rn_forge.fastapi_adapters`? Free today, a breaking rename later |
| fastapi Phase 5 | If web's ASGI middleware needs no FastAPI adaptation at all, ship no module — confirm rather than adding a wrapper for symmetry |
| ~~django Phase 2 / web §4.3~~ | **Resolved (2026-09-12): forward-only on both stacks.** No `reverse` on the web `Cursor`, no `previousPageToken`; recorded in both plans |

**Commons Part D.8/D.9 are open by decision, not by effort.** Cutting a release pushes a tag, which
the plans' ground rules forbid without being asked; the pins already name the tags they will get. See
the commons plan's "What D.8 and D.9 need".

**Commons Phase 18.4 is resolved:** use `rn-forge-tooling` for shared installer mechanics and the
parameterized state machine. Keep `$RNF_HOME`, product coordinates, retention/uninstall policy and
product-specific validation in agentkit and kiln. Taskkit remains a reference donor; do not create
`rn-forge-selfkit`.

Two further decisions are **specified work, not gates** — an implementer performs them and records
the result: the `asgi-correlation-id` and `rfc9457` evaluations in web Phase 0.2. The plan states the
pass/fail criteria and what each phase contains under either outcome.

## Standing rules for every plan

- The workspace **design principles** (README / CLAUDE.md) bind all of these: don't reimplement a
  proven library; wrap it thinly for one design language; keep package boundaries; pykit is upstream.
- **Wire conventions come from published standards where one exists, not from house taste.** Settled
  and normative for both framework packages: RFC 9457 for errors, RFC 9110/6585 for preconditions
  (412/428), [AIP-158](https://google.aip.dev/158) for pagination (`pageSize`/`pageToken`/
  `nextPageToken`, clamped never rejected), RFC 8288 for the additive `Link` header, RFC 6750/7617 and
  OIDC for auth, OpenAPI **3.1.0** for schemas, and camelCase on the wire with `snake_case` in Python
  (Google JSON Style Guide / Microsoft REST Guidelines / proto3 JSON mapping). They live in web Phase
  9.1's `api-conventions.md`; a package that needs to deviate raises it there rather than locally.
- **Django and FastAPI are held to the same wire by a shared test, not by review.** `rn-forge-web`
  ships the scenario table (Phase 11) as framework-free data; each framework package drives its own
  stack through it. A decision with no case in that table is a decision that will drift.
- **A unified model base class, repository protocol or serializer abstraction is permanently out of
  scope** — see the web plan's "The unification boundary". What is shared is vocabulary
  (`model-conventions.md`) and wire shapes. The deferred `rn-forge-sqlalchemy` is a **sibling** of the
  two framework packages, not a step toward merging them.
- **cims and intellibench are prior art, not compatibility constraints.** Both are being respecified
  and reimplemented against these libraries. Where a survey found a weaker design, the plans fix it.
- The Python floor stays **`>=3.14`** across the workspace. The 3.12 floor an earlier draft proposed
  is void (web plan Phase 0.1).
- Every phase ends with its own validation command block, and every one of them includes
  `uv run lint-imports`. After standardization plan Phase F.1 regenerates pykit's skeleton, `task
  validate` is what CI runs and the `uv run …` forms are its inner primitives.
- **Adding a package is a repo-shape change.** pykit is the `python-lib` archetype (kiln D53):
  beyond the workspace members/sources/dependency group, a new package goes into
  `[archetype.python-lib] packages` in `.rn-forge/kiln/config.toml` (it drives the generated CI
  matrix, build and release jobs), needs a `.rn-forge/kiln/state.json` re-seed via `kiln apply`, and
  joins the root `mkdocs.yml` nav and `docs/index.md`. Those kiln files do not exist before Phase
  F.1 — do not create them early.
- **Consumers are archetypes, and a claim needs a golden repo.** intellibuild is `python-web-api`
  (`framework = fastapi`); the cims successor is `python-web-app` (`framework = django`). Under kiln
  ADR-0005 a claim not demonstrated in a runnable golden repo is not demonstrated — the rule that
  caught standardization Phase C shipping ADR-0009 without evidence.
- Nothing is committed or pushed — plans leave the working tree for review.
