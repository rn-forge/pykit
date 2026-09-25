# Documentation structure review and refactor handoff

**Date:** 2026-09-23 · **Status:** review; proposed refactor, not implemented.
**Baseline:** pykit `feature/upgrade`, HEAD `653ac47`, plus the working tree.
**Second review:** 2026-09-23, against HEAD `9af1705` — see
[Second review](#second-review-2026-09-23), [Open work register](#open-work-register)
and [Writing rules for the rewrite](#writing-rules-for-the-rewrite).
**Audience:** owner deciding the documentation model; implementing agent carrying out the refactor.

## How to use this document (implementer: read this first)

1. Read [Second review](#second-review-2026-09-23) — it corrects parts of the first review.
2. The [Open work register](#open-work-register) is the list of everything not done. Every row
   must end up in exactly one epic or feature file. Nothing in it may be dropped.
3. The [Closed items](#closed-items-do-not-reopen) list is work that was rejected, withdrawn
   or superseded. None of it may appear as open work.
4. Follow [Writing rules for the rewrite](#writing-rules-for-the-rewrite) for every page you
   write, then the five batches in
   [Implementation instructions](#implementation-instructions-for-a-smaller-model).
5. Where the two reviews disagree, the second review wins.

## Recommendation

Adopt kiln's root documentation taxonomy: `architecture`, `guides`, `runbooks`,
`releases`, `specs`, `adr` (singular), and `plans` for evidence/history. Keep
consumer documentation with its owning package, including its `guides/`, `api/`
and executable examples. Keep the combined MkDocs site and all seven standalone
package sites. Do not duplicate kiln's entire documentation infrastructure or
create seven miniature ADR/spec/release trees inside the packages.

This is an information-architecture and content reconciliation task, not just a
file move. Extract current decisions and remaining work from the old plans;
preserve the plans as historical evidence with a section-to-destination map.
Do not promote superseded proposals into current contracts.

The recommended defaults below make the mechanical work actionable. Questions
that affect release approval or unresolved product behavior remain explicit;
the documentation agent must not settle those by changing code.

## Second review, 2026-09-23

**Verdict:** the first review is accurate, and its direction (kiln's taxonomy, package docs
stay in packages, plans become history) is right. Adopt it with the corrections below.

**Spot-checked and confirmed:** no SQLAlchemy job in `.github/workflows/main.yml`; CI runs
`mkdocs build` without `--strict` (line 195); local tags stop at commons/django `v0.2.2`;
`docs/auth-overview.md` still ends with "My followup thoughts"; kiln's specs use
`epics/E<n>-<slug>/index.md` with `F<n>.<m>` feature files, as described.

**Corrections and gaps:**

1. **No concrete list of open work.** The epic table names containers but not the items that go
   in them, and E6 says "reconcile redaction/SSE" without saying what state they are in. A lower
   model would have to re-derive this from 12,000 lines of plans. Fixed: the
   [Open work register](#open-work-register) lists every open item with its source and target ID.
2. **Redaction and SSE are not built.** Checked the tree: no redaction code in
   `rn-forge-commons`, no `sse` module or `sse` extra in `rn-forge-fastapi`. They are open
   features (F6.1, F6.2), not items to "reconcile".
3. **kiln already owns the release trigger.** kiln's `docs/specs/epics/E7-pykit-release-pin-flip`
   is `deferred` with the entry criterion "the owner declares pykit stable", and its tag order
   (commons → cli → tooling → web → django/fastapi) **omits `rn-forge-sqlalchemy`**. F2 missed
   both. pykit's E9 must link kiln E7 as the trigger, and the missing package is a downstream
   correction for kiln (register row E12).
4. **The status board is staler than F1 says.** `docs/plans/README.md` still calls R3, R4, R9 and
   R10 "uncommitted"; they are committed (`630142c`, `df7a245`, `74b36ff`, `653ac47`). Its header
   says "Updated 2026-09-19" but records 2026-09-23 events. Record these in the ledger; do not
   carry "uncommitted" into any epic.
5. **Q4 is already answered in part.** The board's backlog says the django split must be decided
   "before the release tags". So it is a release gate by the owner's own words; the open question
   is only *what* the decision is. Updated in Q4.
6. **E6 mixed active work with on-demand ideas.** Split: E6 keeps the two active features; the
   "build when a consumer asks" items move to a new deferred epic E13. Kiln-owned acceptance moves
   from E9 to a new epic E12, so E9 holds only pykit's own release work.
7. **Deferred items were scattered and would be lost.** The deferred lists in the commons, web and
   azure plans, and R9's unbuilt SQLAlchemy contents (SQL idempotency store, session helpers,
   readiness checks — checked: none exist in `rn-forge-sqlalchemy/src`), now have register rows.
8. **The text is too dense for the stated reader.** Long sentences, many negations and
   undefined shorthand (D46, R2.5 B8, F3.3) make the instructions easy to misread. The
   [Writing rules](#writing-rules-for-the-rewrite) govern the *output*; the batches below are kept
   but the register and rules are the primary input.

## Review scope and evidence

Read the repository instructions, root README, all root document inventories
and plan structures, their status/decision/acceptance sections, package README
and documentation structures, MkDocs configurations, package manifests, CI,
representative implementation and test references, and kiln's structure rules,
boards, ADR/spec/release examples and docs tooling. This is a documentation
review, not a fresh verification of every historical implementation claim.

Starting inventory, before this report:

| Location | Inventory | Current role |
| --- | --- | --- |
| Root `docs/` | 15 Markdown files, 12,422 lines | 3 top-level pages and 12 files under `plans/`; no formal ADR/spec/release areas |
| Root `docs/plans/README.md` | 422 lines | Status board, dependency graph, release procedure, standing rules and history combined |
| Seven package `docs/` trees | 148 Markdown files | Consumer guides and docstring-driven API reference; web also has an adoption pack |
| Package README files | 7 | Package entry points and installation/module summaries |
| Package MkDocs configurations | 7 | Included by root `mkdocs.yml`; each also builds independently |
| Web adoption examples | 3 Python files | Documentation with test/type-check coupling; not disposable prose |

Primary pykit evidence: the archived status board (`docs/plans/archive/plan-board.md`),
standards re-baseline (`docs/plans/archive/standards-rebaseline-plan.md`),
commons history (`docs/plans/archive/commons-upgrade-plan.md`),
[kiln handoff](../kiln-dependencies.md), and root `mkdocs.yml`.
Kiln evidence paths below are relative to the sibling `../kiln` repository.
They describe the local checkout reviewed, not a promise about its future state.

The working tree was already dirty and changed further during the review,
including pagination and conformance work. Counts and findings are a dated
snapshot. Re-read the affected sources before implementation; preserve every
unrelated edit. This review creates only this document.

## Findings, in priority order

### F1 — The status board cannot reliably identify remaining work

`docs/plans/README.md` says the original close-out is complete, carries older
release instructions, and also says the Django split must be decided before
release. Its consumer-reuse section still describes Phase 5 as in the working
tree and Phase 6 as prospective; `standards-rebaseline-plan.md`, “Effect on other
plans”, says Phase 5 was withdrawn by R3 and Phase 6 delivered by R2.5 B8.
The re-baseline header itself starts “planned” while its later sections record
implementation, and its “Order” still schedules work other sections call done.

**Required change:** one `docs/specs/index.md` board, with status owned by the
corresponding epic/story. Separate implementation, validation, commit and release
facts. Never infer “shipped” from “implemented”, or a fresh test pass from a
historical green validation block. Preserve conflicting claims in the migration
ledger until resolved; do not silently choose the most convenient one.

### F2 — Release scope and mechanics have no single accurate home

The board's “Last: the release” and commons D.8 omit the now-present
`rn-forge-sqlalchemy`. The package is a workspace member, has a site, and declares
version `0.1.0` and a pinned web dependency. `.github/workflows/main.yml` has no
SQLAlchemy package CI invocation. Existing package jobs depend on the import
boundary gate rather than forming the dependency-ordered release chain the
prose describes. `_package-ci.yml` automatically creates and pushes a missing
package tag and a GitHub Release on a push to `main`.

**Required change:** root release coordination page with all seven package tags,
actual dependencies, unresolved gates and evidence; a separate release runbook
that describes the existing workflow accurately. Record missing SQLAlchemy CI
and release-order enforcement as release-readiness work. Do not edit CI or
publish anything during this docs refactor. Merging to `main` is not a harmless
docs-validation step under the current workflow.

Local tag inspection found historical commons/Django tags through `v0.2.2`, not
the proposed new tags. Remote tag state was not queried. A release executor must
check remote refs later; this review does not certify external installability.

### F3 — Current reader entry points advertise removed behavior

`docs/index.md` still describes correlation-ID middleware and FastAPI pydantic
mirrors after R3/R4/R10. `CLAUDE.md` says SQLAlchemy is parked, cites six import
contracts in its orientation, and lists only five sites; the workspace has seven
sites and the root README describes eight contracts. Its opening lifecycle and
strict-dataclass account also predates subsequent decisions.

`packages/rn-forge-web/docs/api/index.md` names removed `context`;
`packages/rn-forge-fastapi/docs/api/index.md` names removed `schemas`.

**Required change:** reconcile these entry points against current package docs,
source, manifests and `.importlinter`. Keep agent instructions in `CLAUDE.md`,
which should point to the new board and routing rules. Keep `AGENTS.md` as its
existing pointer; do not copy kiln's README-as-instruction-home model wholesale.

### F4 — Root strict documentation build currently fails

Executed with existing dependencies, without syncing or installing anything:

```bash
.venv/bin/mkdocs build --strict --site-dir /private/tmp/pykit-docs-review-site
```

**Result: exit 1, “Aborted with 8 warnings in strict mode!”**

- Six warnings are in `docs/01-extraction-from-cims.md`: links to `./README.md`
  and plans assumed to be siblings, including a repeated web-plan link.
- Two are in `docs/plans/fastapi-app-layer-plan.md`: repository-valid links to
  FastAPI's README and wiring guide are outside the root MkDocs document space.
- Additional INFO diagnostics identify stale section anchors in commons,
  lifecycle-retirement, FastAPI-app-layer, web-reuse and web-library plans.
- The root build includes all 13 non-nav historical pages. Omitting a page from
  `nav` does not exclude it from the site or its checks.
- `.github/workflows/main.yml` runs `mkdocs build` without `--strict`.

**Required change:** choose an explicit historical-publication policy; fix
current-page links and check anchors, not just exit status. Do not downgrade
warnings globally to make the migration pass. Root site links to package pages
must use the monorepo's virtual paths, e.g. `rn-forge-fastapi/guides/wiring.md`
from `docs/index.md`, adjusted for the source page's depth.
All seven standalone builds passed, but Django's landing page emits an INFO
diagnostic for `../rn-forge-commons`. Replace that cross-package directory link
with a package-name reference under the existing standalone-site rule.

### F5 — The root authentication page has two audiences and an unresolved note

`docs/auth-overview.md` combines the cross-package ownership graph, detailed
Django/FastAPI setup, rationale and a final “My followup thoughts” paragraph
about SAML-to-JWT login. Its bare `uv add "rn-forge-fastapi[oidc]"` example also
conflicts with the repository's pinned-direct-URL installation model.

**Required change:** move the cross-package explanation to
`docs/architecture/authentication.md`; merge verified setup instructions into
the existing Django auth and FastAPI wiring guides. Preserve the final owner
note as an open question in the deferred auth review. Do not implement or
reinterpret the auth flow. Remove the stale bare-package install command in
favor of the package installation guide's current dependency form.

### F6 — The web adoption pack must not become a monorepo spec by accident

`packages/rn-forge-web/docs/adoption/api-conventions.md`, deployment guidance,
checklist and examples describe how consumers use the shared HTTP contract.
They belong with web even though multiple adapters consume them. Root specs
should link to their current contracts rather than copy them.

However, `adoption/model-conventions.md` claims that every ORM entity has a shared
status enum, natural-key fixture conventions and status-based soft deletion.
The SQLAlchemy `Base`, `AuditMixin`, `VersionMixin` and usage example do not
implement that whole contract. The board also defers AIP-164 soft-delete work.
The guide's blanket version-update wording needs the same comparison with the
actual `update_versioned`/`upsert` contracts.

**Required change:** distinguish implemented common behavior, Django-specific
behavior and application advice. Record unresolved policy in the owning epic;
do not add ORM behavior to make prose true. Preserve the no-shared-ORM-abstraction
decision in an ADR, while keeping consumer-visible vocabulary in the package.

### F7 — Old kiln references cannot safely be renumbered mechanically

`docs/plans/kiln-dependencies.md` names old descriptive ADR filenames and
ADR-0011; pykit's instructions and plans also refer to ADR-0009. The current
kiln tree has `ADR-0001.md` through `ADR-0007.md`. Kiln's own upstream table still
mentions the old lifecycle-namespace proposal after pykit's retirement plan
superseded it.

**Required change:** independently namespace pykit ADRs; retain D/phase/old-ADR
identifiers as historical provenance. Map each live reference by meaning against
kiln's current decision log and context, not by matching numbers. Keep a stable
handoff at `docs/plans/kiln-dependencies.md`, because kiln explicitly refers to
that path. Record downstream corrections for kiln; do not edit the sibling repo.
Kiln's board also explicitly names `cli-lifecycle-namespace-plan.md`; retain a
short historical forwarding page there until that downstream reference changes.

### F8 — Adopting kiln's generator now would broaden and risk this migration

Pykit has no Taskfile, `_areas.yml` or `_structure.md` system today. Its status
board explicitly defers kiln config/state creation until kiln's pykit cutover.
Kiln's docs-nav implementation builds root-area navigation; its site parser does
not treat `!include ...mkdocs.yml` values as Markdown pages. A copied template
would not preserve pykit's monorepo site automatically or validate package sites.

**Required change:** adopt the routing rules and naming now; retain manually
maintained MkDocs nav and its seven `!include` entries. Treat `_areas.yml` as a
human-maintained declaration until an explicit later tooling adoption. Do not
claim structure checks are enforced before the tooling is actually integrated.

## Kiln conventions to adopt, and deliberate adaptations

| Observed kiln convention | Pykit recommendation |
| --- | --- |
| `docs/index.md` for readers, `docs/_structure.md` for routing rules | Adopt; area `_structure.md` files give admission rules, not product behavior |
| `architecture/` explains what exists; `guides/` explains usage | Root architecture covers package relationships; root guides cover selecting/combining packages and repository development; detailed usage stays in packages |
| `runbooks/` is optional | Use for package release and adding a package; both are real monorepo procedures |
| `reference/` is generated and exempted from some structure checks | Do not create a hollow root reference area or move package `api/` there; package mkdocstrings pages are the API reference |
| `adr/ADR-<nnnn>.md`, index, status and scope | Adopt singular `adr`, start local sequence at 0001; do not inherit kiln numbers |
| Epic `E<n>` → feature `F<n>.<m>` → inline story `S<n>.<m>.<k>` | Adopt for active work; summarize completed legacy work in epic tables instead of manufacturing hundreds of story files |
| `planned`, `elaborating`, `in progress`, `done`, `deferred` epic states | Adopt; explicitly distinguish implementation done from release shipped in this library monorepo |
| Done epics have a shipped date | Adapt: `**Implemented:**` evidence for unreleased completed work; `**Shipped:**` only after actual release evidence. No invented dates |
| Feature dependencies and observable acceptance; questions live with work | Adopt; deferred work has entry criteria and no invented release assignment |
| `release-<n>/index.md`, newest-first index, unique scope assignment | Use release numbers for coordinated batches, with an explicit matrix of independent package versions/tags; no new pykit distribution version |
| Releases link scope IDs; they do not repeat story acceptance | Adopt; legacy completed features may be scope rows, with that exception stated |
| `plans/context.md` is history and a migration ledger; plans are frozen | Adopt after a documented normalization step; see archive policy below |
| Generated root navigation from `_areas.yml` | Defer generator integration; preserve current plugin/theme/URL/docstring settings |
| `_*.md` excluded from the built site | Adopt an exclusion covering nested `_structure.md` files as well; verify the rendered output |
| No `README.md` beside `index.md` within docs | Rename the status board and examples README as specified below; package-root READMEs remain |

Kiln sources: `docs/_structure.md`, each area's `_structure.md`,
`docs/_areas.yml`, `docs/specs/index.md`, `docs/plans/context.md`,
`docs/releases/release-2/index.md`, `src/rn_forge/kiln/modules/docs/{nav,site,structure}.py`.
The structure-rule prose is broader than the implementation: the checker accepts
an instruction carrier through AGENTS → CLAUDE indirection, and generated areas
skip some area/naming checks. Do not copy claims of enforcement as facts.

Kiln's `docs/runbooks/carrying-specs-and-decisions.md` also supplies useful
inventory and lossless-mapping guidance. Its procedure targets rebuilt repos;
this proposal deliberately adapts it to an in-place monorepo cleanup. The proposed
epics consolidate overlapping source plans by delivery concern rather than
blindly assigning one epic per old section. The section ledger is mandatory to
make that consolidation reviewable. Do not infer a repo rebuild from that runbook.

## Proposed target tree and ownership

Paths below are proposed deliverables, not existing links.

```text
docs/
  index.md
  _structure.md
  _areas.yml
  architecture/  index.md, _structure.md, workspace.md, authentication.md
  guides/        index.md, _structure.md, choosing-packages.md, development.md
  runbooks/      index.md, _structure.md, releasing-packages.md, adding-a-package.md
  releases/      index.md, _structure.md, release-1/index.md
  specs/         index.md, _structure.md, epics/E<n>-<slug>/...
  adr/           index.md, _structure.md, ADR-0001.md ...
  plans/
    index.md
    _structure.md
    context.md
    kiln-dependencies.md       # stable historical handoff path
    archive/                  # normalized legacy source records
    reviews/                  # this review and later review evidence
packages/<package>/
  README.md
  mkdocs.yml
  docs/index.md
  docs/guides/...
  docs/api/...
packages/rn-forge-web/docs/adoption/...  # remains consumer-owned
```

Root navigation: Home; Packages (the existing seven includes); Architecture;
Guides; Runbooks; Releases; Specs; Decisions; History. Use `index-only` intent for
Releases, Specs and Decisions; their indexes link to the detailed pages. This
keeps package consumers one click from guides without hiding maintainer material.
Do not create a root `reference/` area merely to match kiln's tree.

| Content test | Canonical home |
| --- | --- |
| A user of one installed package needs it | That package's README, guide or API page |
| It describes a contract owned by web and used by both adapters | Web's adoption/API docs; framework wiring remains with its adapter |
| It explains choosing or combining multiple packages | Root guides or architecture |
| It constrains future cross-package implementation choices | Root ADR |
| It is work, acceptance, deferred scope or a blocking question | Root spec epic/feature |
| It assigns work to a release or records package release evidence | Root release page |
| It is a repeated maintainer operation | Root runbook |
| It is a discarded design, review evidence or old phase narrative | Root plans/history |
| It tells an agent how to work | CLAUDE plus routing files; AGENTS remains a pointer |

### Package-by-package disposition

Counts exclude package READMEs and Python examples. Keep all unmentioned package
pages in place; do not rename `api/` to `reference/` for visual uniformity.

| Package | Markdown pages | Disposition |
| --- | ---: | --- |
| commons | 40 | Keep guides and API pages. Part A–G history stays root-side. No root copies of logging/config/console guides |
| cli | 9 | Keep generic command declaration and CLI guides. Lifecycle setup belongs to tooling; decision/history belongs to root ADR/spec |
| tooling | 11 | Keep generation, templates, state and lifecycle installation guides. Product policy/kiln history belongs in root history, not consumer API reference |
| web | 26 | Keep guides, API and adoption pack. Root architecture links to the contract. Correct obsolete API index and qualify model-convention scope |
| django | 40 | Keep settings/models/auth/fixtures/messaging/transfer/OpenAPI/DRF guides and API. Merge Django auth setup from root, not a new duplicate guide |
| fastapi | 14 | Keep wiring/app/transfer/auth/API guidance. Merge relevant root auth setup and remove stale `schemas` description |
| sqlalchemy | 8 | Keep models/concurrency/upsert/pagination/usage docs. Include in root package selection, architecture and release matrix; do not treat it as parked |

Preserve package-specific development details, including Django's test settings
and SQLAlchemy's PostgreSQL test setup. Move historical library-evaluation
narratives (for example Django README “Dependencies and why” and its OpenAPI
guide “Why there is no camelCase dependency”) into root context where they are
history; retain concise current requirements and usage rationale locally.
Package READMEs remain packaging metadata inputs, not pages to delete in favor
of the site. Do not add README synchronization tooling.

Web `adoption/wiring-fastapi.md` is already a “This guide moved” page. Retain a
small package-name pointer consistent with standalone-build rules; remove or
label its obsolete table and fix `adoption/index.md`'s promise of a full adapter
guide. The actual guide stays in FastAPI. Web `adoption/wiring-django.md` teaches
plain-Django composition: label that use case and distinguish it from the
canonical rn-forge-django quickstart; do not silently remove the plain-framework
option. Re-read it at execution time because it changed during this review.

Rename `web/docs/adoption/examples/README.md` to `index.md` for the new docs
convention, and update its nav entry and links. Keep `asgi_app.py`, `django_app.py`
and `fastapi_app.py` exactly where they are. The web tests load the ASGI example
by path; root Pyright excludes the two framework examples explicitly. Moving
these code files would need a separate, unnecessary code/config change.

## Complete root-document disposition

For every extraction, record old file + heading/phase → destination + status in
`plans/context.md`. Historical source copies are not a second current authority.

| Existing file under `docs/` | Required treatment and destination |
| --- | --- |
| `index.md` | Rewrite as concise reader entry point; retain all seven package links; add reader/maintainer routes; remove stale feature descriptions |
| `auth-overview.md` | Split into root `architecture/authentication.md`, existing Django auth/FastAPI wiring guides, and E8's unresolved owner question |
| `01-extraction-from-cims.md` | Move to `plans/archive/01-extraction-from-cims.md`; clearly superseded; map original tiers to E1/E2/E3/E7 without reviving them |
| `plans/README.md` | Extract board to `specs/index.md`; graph to `architecture/workspace.md`; standing decisions to ADRs; release to `releases/release-1/index.md` and runbook; backlog to deferred epics; preserve source as `plans/archive/plan-board.md`; create historical `plans/index.md` |
| `plans/commons-upgrade-plan.md` | Archive original; A–E and G summarize in E1; F plus later retirement in E5; D.8 in E9/release, D.9 and F3.3 in downstream handoff; map rejected Phase 6 and other gates as rejected, not unfinished |
| `plans/web-library-plan.md` | Archive; implemented foundation summarized in E2; current behavior stays web docs; standards revisions point to E4; completed auth/conformance under E2; deferred candidates map to E6/E7/E8/E11 or explicit deferred rows |
| `plans/django-upgrade-plan.md` | Archive; phases 0–13 summarized in E3; later transfer replacements point to E4; split/auth questions to E8; framework-specific usage stays Django docs |
| `plans/fastapi-library-plan.md` | Archive; phases 0–7/6b/6c summarized in E3; Phase 8 is kiln-owned acceptance, not a new pykit implementation story; withdrawn mirrors/middleware designs point to E4 |
| `plans/fastapi-app-layer-plan.md` | Archive; E3 records create_app → FastApiApp supersession via reuse Phase 0; current assembly described only by package wiring/app reference |
| `plans/web-api-reuse-plan.md` | Archive after a phase ledger; remaining redaction/SSE work → E6; Phase 0 → E3; Phase 1 withdrawn → E4/R1; Phase 4 retained → E2/E4; Phase 5 withdrawn → E4/R3; Phase 6 delivered → E4/R2.5 B8 |
| `plans/standards-rebaseline-plan.md` | Archive after mapping every R section; current decision → ADR-0003; implemented R items → E4; R6 → E8; still-open R8 follow-ups → E6 deferred rows or E9 external acceptance where appropriate |
| `plans/cli-lifecycle-namespace-plan.md` | Archive full text as superseded; retain a short historical forwarding page at the old path for kiln's known reference; carry surviving namespace into E5 and tooling's guide, never back into cli |
| `plans/cli-lifecycle-retirement-plan.md` | Archive implemented record; E5 summary and ADR-0005 rationale; package tooling guide remains the `[lifecycle]` contract |
| `plans/azure-library-plan.md` | Archive full design; E7 deferred epic with entry criteria and Phase 4/5/namespace gates; no package scaffold, install guide or release assignment |
| `plans/kiln-dependencies.md` | Keep path; normalize into explicitly historical handoff with links to pykit's new authoritative destinations. Current downstream obligations live in E9/E11. Record old kiln references in context |
| `plans/reviews/docs-structure-review.md` | Keep this report as review evidence; E10 owns actual execution status |

### Detailed harvest rules for the large plans

Do not lose the small items when compressing the long plans:

- **Commons:** map A phases 0–6, B phases 7/8/8b/8c/8d/9, C phases 10–18,
  D.0–D.9, E.0–E.4 and E.1a, F, G, every gated decision and every deferred row.
  Phase 6's OmegaConf rejection must not become “still to implement”. Part D's
  old docs-mechanics placement must be checked against current tooling/kiln
  ownership rather than copied into current package architecture.
- **Standards:** map R1, R2, R2.5 A/B, R3, R4, R5, R6, R7, R8, R9 and R10.1–10.5.
  R10.3 stopped at its probe: record the rejected option, not an incomplete
  implementation story. R5 is evaluation evidence, not four dependency-adoption
  tasks. R9 unparked SQLAlchemy; preserve that decision despite older plans.
- **Reuse:** keep the dependency evaluations and consumer survey as history.
  Do not automatically convert a once-approved library into a newly authorized
  dependency installation. Parked acceptance consumers stay parked. Recheck
  redaction/SSE and R8 pagination leftovers against the live tree before assigning
  their current state; pagination changed while this review was being written.
- **All plans:** preserve rejected alternatives, explicit out-of-scope lists,
  owner decisions, validation dates and downstream ownership. A checkbox and a
  later status paragraph can disagree; record that discrepancy for resolution.

### Proposed epic IDs and minimum deliverables

These IDs are local to pykit. Allocate once; do not reuse kiln IDs by implication.

| Epic directory under `specs/epics/` | Scope and treatment |
| --- | --- |
| `E1-foundation-and-boundaries` | Implemented commons/cli/tooling foundation; compact legacy feature table, implementation evidence, ADR links |
| `E2-http-contract` | Implemented web primitives/auth/conformance; point to package docs for current behavior |
| `E3-framework-adapters` | Implemented Django/FastAPI adapters and application layer; identify replaced designs, kiln acceptance separately |
| `E4-standards-rebaseline` | R1–R10 inventory including SQLAlchemy; distinguish done, rejected and deferred; do not call the whole epic shipped |
| `E5-tool-lifecycle` | Implemented lifecycle retirement and namespace; tooling owns current behavior |
| `E6-consumer-reuse` | **Planned.** Two unbuilt features: F6.1 log redaction, F6.2 SSE. Implemented reuse phases are rows in E3/E4, not here. No release assignment invented |
| `E7-azure-adapters` | Deferred; owner scheduling plus original gates are entry criteria |
| `E8-django-scope-and-auth` | Deferred design review, **but F8.1 (the split) is a release gate** by the owner's own board text |
| `E9-release-readiness` | pykit's own release work: package matrix, CI gaps, installability evidence, the tag cut. Triggered by kiln E7. No release execution authorization |
| `E10-documentation-refactor` | This handoff's execution; completion means content/link/build checks pass, not that packages shipped |
| `E11-framework-codegen` | Deferred; existing import fences are not implemented generators; kiln ownership and entry criteria explicit |
| `E12-kiln-acceptance` | **Added by the second review.** Deferred; tracked here, owned by kiln. Golden repos and kiln-side corrections that can send new work back to pykit |
| `E13-on-demand-features` | **Added by the second review.** Deferred; each row is built only when a named consumer asks. Holds the scattered "deferred — do not build yet" lists |

The full item list for every open epic is the [Open work register](#open-work-register).

Completed legacy work needs one epic index with feature rows, not a retroactive
story for every commit. For active work use `F<n>.<m>-<slug>.md` with `**Depends
on:**`, inline story IDs, `**Status:**`, `**Acceptance:**`, `## Design` if needed,
and `## Open questions`. A release assignment is authoritative only on the
release page. Board release columns are links/projections, not a second roster.

### Proposed ADR harvest

Each record: status/date/scope, Decision, Consequences, Influences, Alternatives
considered, optional Background. Use kiln's readable budget (first three sections
about 300 words; roughly 600 overall unless evidence needs more), not a hard
limit that deletes reasoning. New record date and original decision date are
separate facts. Mark established choices accepted only where the source supports
it; unresolved choices remain proposed.

| File | Decision title | Sources and limits |
| --- | --- | --- |
| `ADR-0001.md` | Libraries follow explicit runtime and tooling boundaries | Root README, `.importlinter`, commons D/E, R9; present graph including SQLAlchemy, no compatibility re-exports |
| `ADR-0002.md` | Packages release independently through pinned git tags | README, commons D.7/D.8, manifests; preserve independent versions, distinguish intended order from CI behavior |
| `ADR-0003.md` | Standards and adopted frameworks precede pykit wrappers | Re-baseline premise/R1/R5/R10 and standing rules; no invented normalization of OpenAPI text |
| `ADR-0004.md` | Frameworks share HTTP contracts without sharing an ORM abstraction | Web unification boundary, R4/R9, conformance source; do not claim all ORM vocabulary is implemented |
| `ADR-0005.md` | Tooling owns lifecycle composition; cli stays generic | Lifecycle retirement decision, commons F as superseded context; namespace survives under `[lifecycle]` |
| `ADR-0006.md` | Optional integrations stay behind explicit extras and import boundaries | README principles, commons G, manifests and facade rules; avoid enumerating volatile dependency versions |
| `ADR-0007.md` | Package usage docs and monorepo governance have separate homes | This proposal; proposed until the owner adopts it |

Routine implementation choices and each rejected library evaluation do not need
separate ADRs. Keep their evidence in context or the owning feature, linked from
the durable standards-first decision. Do not copy kiln's own product-policy ADRs.

## What is done

Checked against `git log` on 2026-09-23. "Done" means implemented and committed on
`feature/upgrade`. **None of it is released** — no new tag exists. Each row becomes a feature row
in the named epic, with `**Implemented:**` and the commit, never `**Shipped:**`.

| Epic | Done work (source plan → commit) |
| --- | --- |
| E1 | commons Parts A–C (`commons-upgrade-plan.md`); Part D layer split D.1–D.7 → `f59c40f`; Part E incl. E.1a strict dataclasses and Part F lifecycle → `757908e`, `37fa7fc`; Part G `StrictModel` (`pydantic` extra) → `231a68e` |
| E2 | web Phases 0–11 → `8b5160b`; §9.1 OpenAPI naming and §10 `OidcAuthenticator` → `37fa7fc`; reuse Phase 4 (`unmapped_exceptions`) — present in `rn_forge/web/problem.py` |
| E3 | django Phases 0–13 → `9d8588c`; fastapi Phases 0–7, 6b, 6c → `3e80dbd`; app layer → `c769562`, then replaced by `FastApiApp` (reuse Phase 0) |
| E4 | R1, R2, R2.5 → `373d6bc`; R3 → `630142c`; R10 (except R10.3) and R5 → `74b36ff`, `c1979a4`; R4 → `df7a245`; R7 → `cc78e19`, `a036a50`; R9 incl. `rn-forge-sqlalchemy` → `653ac47`; R8 → `9af1705` (verify: its message says "pending items") |
| E5 | lifecycle retirement (namespace design carried over) → `1a8241b` |

Commit hashes come from commit subjects. The implementer confirms each with `git show --stat`
before writing it into an epic; a hash that does not match goes into the ledger as a conflict.

## Open work register

Every row here must appear in exactly one epic or feature file after the refactor. Keep the
**Source** text in the ledger so old identifiers stay searchable. "Owner" is who does the work;
"owner decision" means the repository owner must decide before anyone builds.

### Active (status `planned`)

| ID | Item | State checked 2026-09-23 | Owner | Source |
| --- | --- | --- | --- | --- |
| F6.1 | Structured-log secret redaction in `rn_forge.commons.logging` | Not built | pykit | `web-api-reuse-plan.md` Phase 2 |
| F6.2 | SSE frame contract over `sse-starlette`, `sse` extra in `rn-forge-fastapi` | Not built; the dependency was evaluated but not added | pykit; adding `sse-starlette` needs owner approval | `web-api-reuse-plan.md` Phase 3; acceptance by PhotoTidy and Apollo |
| F9.1 | Add `rn-forge-sqlalchemy` to CI | Missing from `.github/workflows/main.yml` | pykit (separate task; not in this docs refactor) | This review F2 |
| F9.2 | Run the CI docs build with `--strict` | CI runs non-strict (`main.yml:195`) | pykit (separate task) | This review F4 |
| F9.3 | Document the real release mechanism: pushing to `main` auto-creates tags via `_package-ci.yml`; decide whether CI must enforce dependency order | Not documented | pykit; owner decision on enforcement | This review F2 |
| F9.4 | Confirm the seven-package release matrix, including `rn-forge-sqlalchemy` | Proposed only | owner decision (Q5) | This review; board "Last: the release" |
| F9.5 | Prove external installability: tags exist remotely, packages install without the workspace override | Not done | pykit, after F9.6 | `fastapi-library-plan.md:777`; `django-upgrade-plan.md:1472` |
| F9.6 | Cut the tags (merge to `main`) in dependency order | Not done; needs the owner's word | owner | README step 12; commons D.8; `commons-upgrade-plan.md:2557`; triggered by kiln E7 |
| F10.1–F10.5 | This refactor, one feature per batch below | Not started | documentation agent | This review |

### Release gate needing an owner decision

| ID | Item | Source |
| --- | --- | --- |
| F8.1 | Whether SAML, Celery, fixtures and messaging leave `rn-forge-django` for their own packages. Must be decided before F9.6 — a later split breaks imports and re-exports are forbidden | README backlog (was R6); `standards-rebaseline-plan.md` R6 |
| Q9 | Are F6.1 and F6.2 in the first release, or deferred to E13? | This review |

### Deferred (status `deferred`, each with entry criteria)

| ID | Item | Entry criterion | Source |
| --- | --- | --- | --- |
| E7 | `rn-forge-azure`: Phases 0–3; Phase 4 (Service Bus) and Phase 5 (Azure Monitor) gates; namespace decision; deferred Azure OpenAI, Azure DevOps, managed-identity Postgres and Entra OIDC adapters | Owner schedules it | `azure-library-plan.md` |
| F8.2 | Auth reviewed as one piece (`rn_forge.django.auth` and the web/fastapi parts), including the SAML-to-JWT note copied verbatim | Owner schedules it | README backlog; `docs/auth-overview.md` "My followup thoughts" |
| E11 | `[codegen]` generators for django and fastapi (fences exist, generators do not) | kiln D2/D37 work starts | README "Waiting on kiln" |
| E13 row | `:batchGet` and `:batchUpdate` handlers | A consumer needs them | README backlog (R8 leftovers) |
| E13 row | AIP-164 soft delete (`deleteTime`, `:undelete`, `showDeleted`) | A consumer needs it | README backlog; R8 owner decision |
| E13 row | Multi-column sorting — to be ideated first (token per term, composite keyset, NULL ordering, conformance case) | Owner starts ideation | README backlog; R8 status |
| E13 row | Multi-tenant row scoping (`ProjectScopedRepository`, isolation hook, RLS) | A second application states its tenancy model | `web-library-plan.md` Deferred |
| E13 row | Rest of `rn-forge-sqlalchemy`: SQL `AsyncIdempotencyStore`, session/unit-of-work helpers, readiness checks | A SQLAlchemy application asks | `web-library-plan.md` Deferred; R9 scope |
| E13 row | CloudEvents envelope builder | The outbox/inbox messaging subsystem needs it | `commons-upgrade-plan.md` Deferred |
| E13 row | Claim-check pattern | A second storage backend is in view | `commons-upgrade-plan.md` Deferred |
| E13 row | `ProductInstaller` shared contract | A second product needs the same contract | `commons-upgrade-plan.md` Phase 18.4 |
| E6 note | Account Portal and IntelliBuild acceptance of reuse phases | Those applications are unparked | `web-api-reuse-plan.md` "Consumer acceptance" |

### Owned by kiln, tracked in E12

pykit does no work here. A gap a golden repo finds comes back as a new pykit feature.

| Item | Source |
| --- | --- |
| `golden/python-app` (commons D.9); `commons-upgrade-plan.md:2558-2559` | commons plan |
| `golden/python-tool` with `[lifecycle]` (kiln F3.3) | commons Part F |
| `golden/python-web-api` (fastapi Phase 8) | `fastapi-library-plan.md:809` |
| `golden/python-web-app-django` | README |
| kiln F4.2 — config manager parses through `StrictModel` | commons Part G |
| kiln F.1 — `[archetype.python-lib] packages` entry and `state.json` re-seed | README standing rules |
| `oasdiff` CI note for golden repos (AIP-180) | README backlog |
| Confirm gateways accept AIP-136 `:verb` paths; record a deviation in R8's successor if not | README backlog |
| kiln E7 tag order omits `rn-forge-sqlalchemy` | Second review, item 3 |
| kiln references to old ADR names, ADR-0009/0011 and `cli-lifecycle-namespace-plan.md` | This review F7 |

## Closed items, do not reopen

These were rejected, withdrawn or superseded. Record each once, in the ledger and on its epic
under *Considered and rejected*. None of them may appear as open work.

| Item | Outcome | Source |
| --- | --- | --- |
| commons Phase 6 (OmegaConf resolver) | Rejected at its gate, 2026-09-07 | commons plan gates |
| web Phase 0.2 libraries (`asgi-correlation-id` and the other candidate) | Rejected | `web-library-plan.md` status |
| reuse Phase 1 (`install_component_schemas`, `openapi_json`) | Withdrawn by R1 | `web-api-reuse-plan.md` |
| reuse Phase 5 (correlation-ID validation) | Withdrawn; replaced by R3 Trace Context | `standards-rebaseline-plan.md` R3 |
| reuse Phase 6 (CORS) | Delivered by R2.5 B8 (`rn_forge/fastapi/cors.py`) | re-baseline R2.5 |
| reuse findings 7–12 (offset pagination, `offload()`, SPA mount, `serve`, settings facade, port container) | Rejected | `web-api-reuse-plan.md` Findings |
| R5 library evaluations (`fastapi-problem`, `fastapi-pagination`, `drf-standardized-errors`, `django-health-check`) | All exempt; no dependency added | re-baseline R5 |
| R10.3 (Starlette `RequestBodyLimitMiddleware`) | Rejected at its probe | re-baseline R10 status |
| `create_app` factory | Replaced by `FastApiApp` | reuse Phase 0 |
| `cli-lifecycle-namespace-plan.md` | Superseded by the retirement plan | README table |
| `X-Correlation-ID`, access-log middleware, `Page<Item>` renaming, FastAPI pydantic mirrors | Removed by R3, R10.2, R1, R4 | re-baseline |
| `previousPageToken` / reverse cursor | Rejected: forward-only | README gates |

## Release documentation design

`release-1` means the first coordinated batch documented by the new structure,
not pykit's first-ever release. Historical tags exist. Explain that distinction
on the release index; do not invent historical batch contents.

Proposed matrix, to be regenerated from manifests at implementation time:

| Package | Declared version | Intended tag | Internal dependency prerequisites |
| --- | --- | --- | --- |
| commons | 0.5.0 | `rn-forge-commons-v0.5.0` | None |
| cli | 0.1.0 | `rn-forge-cli-v0.1.0` | commons |
| tooling | 0.2.0 | `rn-forge-tooling-v0.2.0` | commons, cli |
| web | 0.1.0 | `rn-forge-web-v0.1.0` | commons |
| django | 0.3.0 | `rn-forge-django-v0.3.0` | commons, web; inspect extras separately |
| fastapi | 0.1.0 | `rn-forge-fastapi-v0.1.0` | web; commons via transfer extra |
| sqlalchemy | 0.1.0 | `rn-forge-sqlalchemy-v0.1.0` | web |

A valid dependency order is commons → cli → tooling → web → django/fastapi/
sqlalchemy; cli/tooling are not prerequisites of web. Use actual manifest edges,
including optional extras, rather than treating that example order as a new
coupling. Do not bump versions or update pins merely to match this report.

Entry criteria include owner disposition of E8 and selection of batch scope.
Exit criteria include package/version/ref evidence, current required validation,
external installability without workspace overrides, and explicit release
approval. Link E9 stories for the evidence details. Mark no release `shipped`
until those facts exist. Downstream kiln acceptances are kiln-owned obligations;
only a confirmed pykit gate belongs in the batch's blocking list.

## Questions for the owner

These are review questions, not requests to interrupt this review. Defaults
below guide the documentation refactor if it is assigned as recommended; items
explicitly marked unresolved must remain open in the resulting docs.

| ID | Question | Recommendation / effect |
| --- | --- | --- |
| Q1 | Adopt the taxonomy now, or include full kiln tooling adoption? | **Taxonomy now.** Preserve explicit MkDocs nav; kiln integration remains its separately scheduled cutover |
| Q2 | Should historical plans remain in the published site? | **Repository-only raw archives; publish their index/context and concise history.** This prevents obsolete designs dominating search; detailed evidence remains in Git |
| Q3 | Keep package `api/` and web `adoption/`, or rename everything to kiln area names? | **Keep existing package paths.** Their audience and independent builds already fit |
| Q4 | Is R6/auth merely deferred, or must its disposition be decided before release? | **Split (F8.1): a release gate** — the board already says "decide before the release tags". **Auth (F8.2): deferred**, not a gate. The open part is the split decision itself; do not split packages or declare release readiness |
| Q5 | Does the first coordinated batch include all seven current workspace packages? | **Recommend all seven, including SQLAlchemy.** Matrix is a proposed scope until confirmed; unresolved CI coverage is not evidence of exclusion |
| Q6 | Should model conventions require SQLAlchemy status/natural keys/soft delete? | **Document only implemented guarantees; classify the rest as advice or unresolved design.** Any stronger requirement needs a separate feature decision |
| Q7 | What should become of the SAML-to-JWT follow-up note? | **Carry verbatim into deferred auth review.** Do not resolve auth design during document restructuring |
| Q8 | Preserve every old published page URL, or migrate links once? | **Update internal links and retain only known external handoff paths.** Add a redirect/tombstone only for a confirmed external consumer; no redirect dependency by default |
| Q9 | Do log redaction (F6.1) and SSE (F6.2) go into the first release? | **Unresolved.** Record under E6 as `planned` with no release assignment until answered. If deferred, move them to E13 keeping their IDs |
| Q10 | Should `rn-forge-sqlalchemy` join kiln E7's tag order? | **Yes if Q5 says all seven.** Record as a kiln correction in E12; do not edit kiln |

## Archive and link policy

Kiln freezes historical files without editing even their links. Pykit's current
plans already contain broken links, so copying that rule literally conflicts
with a clean root site build. Use this explicit adaptation:

1. Record baseline paths and hashes before the move. Original bytes remain in
   Git; preserve uncommitted content too, rather than replacing it with HEAD.
2. Move legacy plans under `plans/archive/`, allowing only a historical banner
   and link/path corrections. Record these permitted normalizations in context.
   Do not rewrite old designs to sound current.
3. Freeze after normalization. Subsequent corrections go in context. Every
   source section has a destination or an explicit historical-only/rejected row.
4. Exclude `plans/archive/**` from MkDocs rendering/search with `exclude_docs`.
   Do not use `not_in_nav` as an exclusion: those pages still build. Check nested
   routing-file exclusions too. Publish `plans/index.md` and `plans/context.md`.
5. Published pages must not link relatively into excluded archives or to
   `_structure.md`. Use source-location text in the ledger, or repository blob
   links with a verified repository/ref when useful. Do not invent a future
   commit permalink. Repository-only routing files may link to source files.
6. Keep `plans/kiln-dependencies.md` as a published historical handoff with live
   pointers, and the namespace-plan forwarding page for kiln's known reference.
   For other moves, update live inbound links,
   nav and anchors. Avoid leaving a README stub beside a new index.
7. Keep package standalone links inside their own site. Use another package's
   name when directing users to it, as CLAUDE requires. Root aggregate links use
   the MkDocs virtual package paths; Git-source links and site links are distinct.

History retains supersession explicitly: original proposal → later decision →
current canonical home. It does not become an alternative spec board.

## Writing rules for the rewrite

The new pages are read by people and agents who have not read the old plans. Write so that a
reader can understand a page alone, and can follow any item from the board to its details and
back in one click each way.

### Language

- Short sentences, one idea each. Active voice: "`rn-forge-web` owns the problem format", not
  "the problem format is owned by".
- Say what is true now. Put history in `plans/context.md`, not in current pages. No
  "previously", "after the review", "R3 changed this" in architecture or guides.
- Prefer positive statements. Write "Django keeps `django-import-export`" rather than a chain of
  "not X, not Y".
- Define every shorthand on first use in a page, or do not use it. Old IDs (D46, R2.5 B8, F3.3,
  AIP-136) appear only in the ledger, ADR *Background*, or next to a plain-language name:
  "pinned git tags (kiln D46)".
- Use the same name for the same thing everywhere: package names as `rn-forge-web`, import paths
  as `rn_forge.web`, statuses exactly as `planned`, `elaborating`, `in progress`, `done`,
  `deferred`.
- One fact, one home. Other pages link to it; they do not restate it.

### Page shape

- Every page opens with one or two sentences saying what it covers and who it is for.
- Status and ownership sit at the top, as labelled lines: `**Status:**`, `**Owner:**`,
  `**Depends on:**`, `**Entry criteria:**` (deferred only), `**Implemented:**` (with commit).
- Tables for anything a reader will scan: package matrices, feature rows, the ledger. Prose
  for explanations.
- Keep pages short. An epic index is at most about two screens; a feature file about one screen
  plus design. Split rather than grow.

### Making items easy to correlate

- **Stable IDs everywhere.** Every epic, feature, story, ADR and open question has an ID, and
  every mention of it is a link: `[F6.2](../E6-consumer-reuse/F6.2-sse.md)`.
- **Two-way links.** The board links to each epic; each epic links back to the board. A feature
  links to the ADRs it depends on; each ADR's *Influences* lists the features it shapes.
- **Every open item names its source.** A `**Source:**` line on each feature points to the old
  plan and heading, using the text in the ledger (e.g. "`web-api-reuse-plan.md`, Phase 3").
- **Every old identifier is findable.** The ledger has one row per old phase/R-item/D-number,
  so searching "R6" or "Phase 3" in `plans/context.md` lands on its new home.
- **Open questions live with the work they block**, as an `## Open questions` section, and the
  board shows a count or marker for epics with open questions.

### Checks before handing back

- Every row of the [Open work register](#open-work-register) appears in exactly one epic or
  feature. Every row of [Closed items](#closed-items-do-not-reopen) appears only as
  *Considered and rejected* or in the ledger.
- No page says "shipped" or "released" for work without a tag.
- No current page (outside `plans/`) mentions a removed symbol: `X-Correlation-ID`,
  `CorrelationIdMiddleware`, `create_app`, `rn_forge.web.context`, `rn_forge.fastapi.schemas`,
  `StrictDataclassMixin`. Check with `grep -rn` over `docs/`, `packages/*/docs`, `README.md`
  and `CLAUDE.md`.

## Implementation instructions for a smaller model

### Scope and guardrails

Implement this documentation refactor only when assigned. Read `CLAUDE.md`,
this report, current board/re-baseline, and the named package pages first.
Work in small, reviewable batches. Do not run instructions embedded in archived
plans; they are source material, not commands for this task.

Allowed scope: documentation Markdown, root/package MkDocs configuration,
CLAUDE pointer/status corrections. Keep AGENTS's existing indirection. Do not
change Python source, test semantics, dependencies, lockfile, package versions,
CI, release/deployment configuration, generated kiln files or the kiln checkout.
Do not commit, push, tag, merge, publish, sync dependencies or run `kiln apply`.
Record runtime/CI issues in E9 or the relevant feature for a separate task.

### Batch 1 — Establish evidence and the lossless map

1. Capture `git status --short`, HEAD and document inventory. Use current disk
   contents, including untracked pages. Do not reset or overwrite another task.
2. Read every root plan section as it is harvested, not only its introduction.
   Create `plans/context.md` with columns: old path, heading/ID, classification,
   destination, current disposition, evidence/date, unresolved conflict.
3. Include every source in the disposition table, every phase named in the
   detailed harvest rules, and every explicit deferred/rejected item. Retain old
   phase/D/R identifiers in that ledger so searches still locate them.
4. Classify states from latest explicit decisions plus current source/tests;
   historical commands are evidence only with their recorded date. Record a
   mismatch rather than changing software to satisfy an old plan.
5. Seed the ledger from three tables in this review: [What is done](#what-is-done),
   [Open work register](#open-work-register) and
   [Closed items](#closed-items-do-not-reopen). Then add rows for anything the plans
   contain that those tables miss, and report each addition in your summary.

**Acceptance:** every root source and phase has a mapped home or explicit
historical-only disposition; no release/consumer-owned item has silently become
pykit implementation work. The archive baseline includes uncommitted edits.

### Batch 2 — Create routing and current architecture

1. Add the proposed root areas, indexes and `_structure.md` files. `_areas.yml`
   uses kiln's version-1 area schema, without `reference`; note that nav remains
   manual. Add only areas listed in the target tree.
2. Write `architecture/workspace.md` from actual package manifests and
   `.importlinter`; link package docs for internal details. Write the root guides
   and runbooks by extracting relevant README/board prose, retaining compact
   root README entry points rather than two complete copies.
3. Split auth as specified; unresolved SAML content goes to E8. No auth behavior
   change. Qualify model conventions without deciding unresolved product scope.
4. Add ADRs with source provenance; add compact legacy epic summaries and
   concrete active/deferred feature records as specified. Do not invent ship
   dates or acceptance outcomes to populate the template.

**Acceptance:** each current statement has one authoritative home; each new ADR
is a decision rather than a feature description; installed-package users still
find usage in their own package docs.

### Batch 3 — Cut over status and release coordination

1. Populate the spec board with each epic in exactly one state group. Feature
   stories own task state; epic/board summaries point to it. Create one feature
   file per `F` row of the Open work register (E6, E8, E9, E10); deferred epics
   (E7, E11, E12, E13) are one `index.md` each, with the register's rows as a table.
2. Create the proposed release batch with the current seven-package manifest
   matrix and Q4/Q5 unresolved status. Release scope uses stable IDs; remaining
   gates/CI gaps have E9 stories. Keep deferred work out of invented releases.
3. Normalize and archive old plans; replace the historical plan board with
   `plans/index.md`, keeping its source in the archive. Normalize the stable
   kiln handoff and record necessary downstream updates without editing kiln.
4. Update CLAUDE's start-here link to `specs/index.md`, and its routing to
   `docs/_structure.md`, `docs/index.md`, ADRs and history. Remove stale timeline
   narration rather than reproducing the board there.

**Acceptance:** new sessions reach current work first; old plans cannot be
mistaken for instructions; no “implemented” state implies a release occurred;
every open owner question has an owning epic/feature.

### Batch 4 — Reconcile navigation and consumer pages

1. Update root nav in place, preserving all seven includes, monorepo plugin,
   mkdocstrings source paths/options, theme, site output and URL mode.
2. Add exclusions for routing files and raw archives; retain history entry pages.
   Do not lower link-validation severity globally.
3. Apply the precise package index/wiring fixes from F3/F6 and the package table;
   rename only the web examples README to index, adjusting its nav and inbound
   references. Keep all three Python example paths unchanged.
4. Update Markdown links and anchors against their actual rendered targets.
   Search README, CLAUDE, all docs, configs and tests for moved filenames; inspect
   matches before replacement so old identifiers in history stay meaningful.

**Acceptance:** root and standalone sites resolve their intended local links;
archives and `_structure.md` do not appear in output/search; package pages remain
reachable; no implementation/test/manifest file changed as collateral damage.

### Batch 5 — Validate and report

Use existing dependencies. If they are unavailable, report the blocker; do not
install dependencies without authorization. For a full docs refactor, build the
root plus all seven standalone sites because root assembly cannot prove isolation.
Use temporary output directories to avoid overwriting a user's existing preview:

```bash
uv run --no-sync --group docs mkdocs build --strict --site-dir /private/tmp/pykit-docs-refactor-root
```

Run the same command from each `packages/<pkg>` directory, with a distinct output
path `/private/tmp/pykit-docs-refactor-<pkg>`. If `uv` attempts unavailable cache
access, use the already-installed root `.venv/bin/mkdocs` executable directly
from that package directory, as in this review. Do not solve it by syncing.

Also perform these narrow checks:

- `git diff --check`; inspect the final file list and preserve pre-existing edits.
- Inspect build logs for missing-anchor INFO diagnostics even on successful
  builds; strict mode alone did not fail on these in the baseline.
- Check links in changed current pages and indexes, including reference-style
  links and heading fragments. Validate actual Markdown-generated anchors, not
  guessed substitutions. Check raw archive source links separately from site links.
- Confirm 7 package includes and all API directive targets still resolve; verify
  root Home, one page from each area, a deep feature/story link, one ADR, release
  matrix, and each package's home/guide/API in the rendered output.
- Compare the migration ledger to the source inventory and section headings.
  Check duplicate epic memberships, missing story IDs, duplicate release scope
  assignments, unanswered questions and rejected work accidentally marked planned.
- Check that unchanged example Python paths still exist. No broad Python test,
  lint or type-check run is necessary if only documentation and nav changed.
  If code would need to change, stop that part and report it outside this scope.

Finish with changed-document summary, exact command outcomes, unresolved owner
questions and remaining pre-existing blockers. Never copy “all green” from a plan.
Do not call the refactor complete while active links, harvest mappings or required
builds remain unresolved.

## Review validation record

- Root strict build: **failed with 8 warnings**, detailed in F4. Full local log:
  `/private/tmp/pykit-docs-review-build.log` (temporary evidence, not a repo artifact).
- All seven standalone package strict builds: **passed, exit 0**, using the
  existing root `.venv/bin/mkdocs` from each package directory. No WARNING/ERROR
  diagnostics. Django reports one unresolved-directory-link INFO diagnostic
  described in F4. Logs: `/private/tmp/pykit-review-rn-forge-<package>.log`.
- Root strict build repeated after adding this report: the same 8 pre-existing
  warnings, none from this report. All four report Markdown links resolve;
  whitespace/fence checks and `git diff --check` passed.
- Local manifests, workspace membership, nav entries, CI invocations and tag list
  inspected. Remote releases, deployment state and fresh runtime test results
  were not checked; no release-readiness claim is made.
- No refactor, dependency installation, commit, push or release performed.
- Second review (2026-09-23, HEAD `9af1705`): checked the CI workflow, local tags,
  `docs/auth-overview.md`, kiln's `docs/specs/_structure.md` and E7, the source trees of
  `rn-forge-commons`, `rn-forge-fastapi`, `rn-forge-web` and `rn-forge-sqlalchemy`, and
  `git log` for the commit mapping. No build or test was re-run.
