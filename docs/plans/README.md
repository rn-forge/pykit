# pykit plans

Five documents, one workspace. This page is the **execution order** — read it before picking up any
plan, because several phases are blocked on phases in other documents and none of the plans repeats
the whole graph.

## The documents

| Document | Scope | Status |
| --- | --- | --- |
| [`commons-upgrade-plan.md`](./commons-upgrade-plan.md) | `rn-forge-commons` — library consolidation (Part A) + new capability (Part B) | Ready |
| [`web-library-plan.md`](./web-library-plan.md) | **New** `rn-forge-web` package — framework-agnostic HTTP primitives | Ready |
| [`django-upgrade-plan.md`](./django-upgrade-plan.md) | `rn-forge-django` — adapters over web/commons + new Django-only modules | Ready |
| [`azure-library-plan.md`](./azure-library-plan.md) | **New** `rn-forge-azure` package — Azure adapters for commons protocols | Ready |
| [`01-extraction-from-cims.md`](./01-extraction-from-cims.md) | The original cims survey | **Superseded — background only** |

`01-extraction-from-cims.md` is the survey the other four grew out of. Its recommendations have been
split, re-decided and in places reversed by the newer plans. **Do not implement from it.** Read it
only to understand where something came from.

## Dependency direction

```
rn-forge-commons  ←  rn-forge-web  ←  rn-forge-django
       ↑
rn-forge-azure
```

`rn-forge-web` never imports a web framework. `rn-forge-azure` depends on commons only — never on web
or django. Both rules are enforced by grep checks in the respective Phase 0s.

## Execution order

Phases within a plan run in their own order unless noted. These are the **cross-plan** edges:

| Step | Do this | Blocked on | Why |
| --- | --- | --- | --- |
| 1 | commons Part A (Phases 0–5) | — | Self-contained; Phase 6 is gated |
| 2 | commons Phase 7 (env guards) | — | Trivial; django Phase 6.2 needs it |
| 3 | commons Phases **8b, 8c, 8d** (messaging / secrets / objects protocols) | — | Small, no new deps, and **four** downstream phases are blocked on them |
| 4 | **web Phase 0** (scaffold + library evaluations) | — | Blocking; decides what Phases 1/2/7 contain |
| 5 | web Phases 1–8 | web Phase 0 | In order; Phase 8 is the curated API + docs |
| 6 | web **Phase 9** (consumer context pack) | web Phases 1–8 | The hand-off artifact for application specs |
| 7 | azure Phases 0–3 | commons 8c, 8d | Key Vault needs `SecretStore`; Blob needs `ObjectStore` |
| 8 | django Phases 0, 2, 5, 8, 9, 12 | commons Part A | Independent of the web package |
| 9 | django Phases 1, 3, 4, 6.1, 7 | web Phases 1–6 | All five are adapters over `rn_forge.web` |
| 10 | django Phase 6.2 | commons Phase 7 | Thin wrapper over `Environment.require` |
| 11 | commons Phase 8 (resilience) | — | Redesign first: see web plan §A.3 |

Steps 1–3 and step 4 are independent of each other and can run in parallel. Step 9 is the one most
likely to be started too early — five django phases will silently reimplement the web package if its
phases have not landed.

## Decisions needed before implementation starts

Six phases are **gated** and need a human decision, not an implementer's judgement. An agent that
reaches one should stop and record the question, not guess:

| Gate | Question |
| --- | --- |
| commons Phase 6 | Replace the `config.py` resolver with OmegaConf? Has an explicit abort gate |
| commons Phase 9 | Adopt structlog as a front-end over `AppLogger`? Both surveyed apps use structlog |
| django Phase 10 | Build outbox/inbox messaging? Needs a committed consumer + a PostgreSQL test job |
| django Phase 11 | Celery integration? |
| azure Phase 4 | Service Bus `MessageBus` adapter? Depends on django Phase 10's outcome |
| azure Phase 5 | OpenTelemetry export to Azure Monitor? |

Two further decisions are **specified work, not gates** — an implementer performs them and records
the result: the `asgi-correlation-id` and `rfc9457` evaluations in web Phase 0.2. The plan states the
pass/fail criteria and what each phase contains under either outcome.

## Standing rules for every plan

- The workspace **design principles** (README / CLAUDE.md) bind all of these: don't reimplement a
  proven library; wrap it thinly for one design language; keep package boundaries; pykit is upstream.
- **cims and intellibench are prior art, not compatibility constraints.** Both are being respecified
  and reimplemented against these libraries. Where a survey found a weaker design, the plans fix it.
- The Python floor stays **`>=3.14`** across the workspace. The 3.12 floor an earlier draft proposed
  is void (web plan Phase 0.1).
- Every phase ends with its own validation command block. Nothing is committed or pushed — plans
  leave the working tree for review.
