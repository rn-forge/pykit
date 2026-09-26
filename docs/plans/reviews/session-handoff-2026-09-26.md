# Session handoff: pykit review close-out and the pykit → kiln feedback loop

**Date:** 2026-09-26 · **Purpose:** continue this discussion in a new chat. Read this first, then the files it links. Excluded from the site, like the rest of `plans/reviews/`.

## The operating model

- **kiln** is the generator. It scaffolds standardized golden repos for several archetypes (`python-app`, `python-tool`, `python-lib`, `python-web-api`, `python-web-app`, …). Its standard lives in `kiln/docs/reference/standard-repo.md` and its Jinja templates.
- **pykit** is the `rn-forge-*` library workspace (seven packages). Eventually kiln regenerates pykit's skeleton as a `python-lib` repo (kiln F6.1), and pykit then uses kiln's structure and docs tooling.
- **Meanwhile**, pykit improves as the golden repos are reviewed. Whatever pykit learns (library code, docs structure, CI/CD, conventions) should feed back into kiln, so the goldens kiln generates pick it up.
- **Governance rule (pykit ADR-0008, 2026-09-26):** pykit is accepted by its own specs and tests. Downstream repos are sources of requirements, never gates, and pykit's docs don't track another repo's work.

## What this session did

### 1. Closed the two pykit doc reviews

Sources: `docs/plans/reviews/docs-structure-review.md` and `docs-refactor-audit.md`, both now banner-closed and excluded from the site. Every answer is recorded in `docs/plans/context.md`, "Owner answers, 2026-09-26", and the close-out is spec feature F10.7.

| Question | Answer |
| --- | --- |
| Q4 Django split | Keep SAML, Celery, fixtures and messaging in `rn-forge-django`; revisit with the auth design (F8.2). F8.1 done; E8 deferred. |
| Q5 release scope | All seven packages in release-1 (F9.4 done). |
| Q9 F6.1 and F6.2 | Both deferred (E6); `sse-starlette` dependency approved (S6.2.1). |
| Q10 kiln tag order | Withdrawn under ADR-0008. |
| S9.3.2 partial release run | A failed package job blocks only its dependents, and CI runs only the packages a change affects plus their dependents. The workflow change is new story S9.3.3. |
| Q1–Q3, Q7, Q8 | pykit follows the shared rn-forge docs standard (ADR-0007, accepted). Package `docs/api/` → `docs/reference/`; web `docs/adoption/` → `docs/guides/`. Every published page passes strict link checks; the archive and reviews are excluded. |
| Downstream as gate | New ADR-0008. E12 (kiln acceptance) withdrawn; its golden-repo checks became F9.8, which scaffolds a CLI app, a tool, a FastAPI service and a Django app from built wheels. The kiln handoff page and namespace forwarding page are to be deleted. |

Validation at the end of that step: root and all seven package sites build `--strict` (exit 0); web example tests (64) and pyright pass; `git diff --check` and `uv lock --check` pass.

### 2. Wrote a kiln plan

`kiln/docs/plans/pykit-docs-alignment.md` (status: proposed; listed in kiln's plans index; kiln nav regenerated; kiln `docs:structure` and `docs:build` pass). It records the result of running kiln's docs checker on pykit: clean on areas, naming, ADR status and the instruction pointer. All 40 findings are links, and they come from one gap: the standard has no model for per-package docs sites. Recommendations R1–R6:

- **R1:** `python-lib` uses per-package sites included into a root site (pykit's layout), not one root site.
- **R2:** a new `include` area kind in `_areas.yml`, so the nav generator emits the package includes; package navs are generated too.
- **R3:** link checks resolve MkDocs monorepo paths into package sites and reject a package page that links outside its package.
- **R4:** checks honor `exclude_docs`.
- **R5:** a fixed package docs shape (`index.md`, `guides/`, `reference/`, no governance areas).
- **R6:** ADR-0008's rule becomes part of the standard for every repo.

It also lists six kiln pages that are now wrong about pykit: the board's upstream table, E5's upstream note, E7, `context.md`'s handoff rows, `intellibuild.md`, and F6.1.

## Current state and pending actions

Nothing is committed in either repo.

**pykit, for the owner to run** (auto-mode blocked file deletions):

```bash
cd rn-forge/pykit
rm docs/adr/ADR-0009.md
mv <session scratchpad>/ADR-0008.md docs/adr/ADR-0008.md   # new ADR-0008 text; replaces the untracked Trace Context copy
git rm docs/specs/epics/E12-kiln-acceptance/index.md docs/plans/kiln-dependencies.md docs/plans/cli-lifecycle-namespace-plan.md
```

If the scratchpad copy is gone, ADR-0008's text is recoverable from the summary above; the ADR index already lists its title, "pykit is accepted by its own specs and tests".

- **Safety net:** `refs/snapshots/closeout-2026-09-26` in pykit holds the full working tree (untracked files included) from before the edits. Delete it with `git update-ref -d refs/snapshots/closeout-2026-09-26` after committing.
- **Branch pins (S9.7.1):** all internal pins name `feature/upgrade` in the working tree. The clean-install check can pass only after they're pushed.
- **Package renames:** the background agent's `git mv` renames are staged; everything else is unstaged.

**kiln:** the new plan, its index entry and one nav line are uncommitted. The owner's own uncommitted kiln work (runbook deletion, E4 edits, `.rn-forge` changes) was not touched.

## Open points

1. **The feedback-loop mechanism** — the main topic for the next chat; see the recommendation below.
1. **The kiln plan's questions:** R1 (per-package sites or one site), R6 (a rule for every repo?), and whether F6.1's pykit cutover is kiln's work or pykit's.
1. **Judgement calls to confirm:** F9.8 (scaffolded acceptance) and S9.3.3 (CI scoping) were added to release-1's scope. S6.1.1 and S6.1.3 were retired, and S6.2.4 was rewritten to use F9.8's FastAPI scaffold.
1. **Instruction-file model:** kiln treats README as the single prose home with `CLAUDE.md` as a pointer; pykit keeps agent instructions in `CLAUDE.md`. The standard should pick one, ideally before F6.1.
1. **pykit's next work:** push the pins, then S9.3.3, F9.1 (SQLAlchemy CI), F9.2 (strict docs CI) and F9.8.
1. **Later cleanup:** before deleting `plans/archive/` and `plans/reviews/`, record in `context.md` the last commit that holds them.
1. **A small kiln bug:** kiln's nav titles `plans/reviews/index.md` "Overview", a second one under Plans.

## Recommendation: how pykit feeds kiln

Treat the four kinds of change differently. Only one of them flows automatically today.

| Kind of change | How it reaches the goldens today | Recommendation |
| --- | --- | --- |
| Library code (commons, cli, tooling, web, django, fastapi, sqlalchemy) | **Automatically.** Goldens and kiln pin pykit's `feature/upgrade`, so the next lock picks it up. After release-1, a pin bump does. | Nothing to add. Keep `feature/upgrade` installable (ADR-0004), and let F9.8's scaffold tests catch breakage before kiln sees it. |
| Docs structure and content rules | Manually: kiln's seeded `_areas.yml` and `_structure.md`, and the standard page | Port each accepted change into kiln's seeded files and standard, as the kiln plan does now. |
| CI/CD | Manually: kiln's `cicd` templates render the workflows; pykit still has its own `_package-ci.yml` | Prove a CI idea in pykit (for example S9.3.3's change-scoped, dependency-ordered jobs), then port it into the `python-lib` CI template. |
| Conventions and decisions (ADRs, spec rules) | Manually | Put rules meant for every repo into kiln's seeded `specs/_structure.md` and `adr/` guidance, and keep pykit-only decisions in pykit. |

**Where the tracking lives.** ADR-0008 says pykit's docs don't track kiln's work, so the intake belongs in kiln. Keep one kiln-side intake, a standing plan or a deferred epic, such as "Standard changes proven in pykit". Each row names the pykit commit or ADR, the kind of change, and the kiln target (template, seeded file or standard section). `pykit-docs-alignment.md` is its first entry. pykit's only job is to write a change up clearly: an ADR, a spec feature, or a commit message saying "standard candidate".

**End state.** After F6.1, pykit is a kiln-generated `python-lib` repo, and the flow reverses. A structural change is made in kiln's templates first and reaches pykit through `kiln apply`, just as it reaches every golden. Until then, the intake above keeps the two from drifting. The earlier F6.1 lands, the less there is to port by hand, which argues for doing R1–R5 soon.

## Files to read in the next chat

- pykit: `docs/specs/index.md` (board), `docs/adr/index.md`, `docs/plans/context.md` ("Owner answers, 2026-09-26"), `docs/specs/epics/E9-release-readiness/`, `docs/runbooks/releasing-packages.md`.
- kiln: `docs/plans/pykit-docs-alignment.md`, `docs/reference/standard-repo.md`, `docs/specs/index.md`, `docs/specs/epics/E6-rebuild-the-repos/F6.1-pykit-skeleton.md`, `src/rn_forge/kiln/modules/docs/{nav,site,structure,areas,policy,scaffold}.py`.
