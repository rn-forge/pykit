# Documentation structure review and refactor handoff

**Date:** 2026-09-23 · **Status:** review; proposed refactor, not implemented.
**Baseline:** pykit `feature/upgrade`, HEAD `653ac47`, plus the working tree.
**Audience:** owner deciding the documentation model; implementing agent carrying out the refactor.

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

Primary pykit evidence: [status board](../README.md),
[standards re-baseline](../standards-rebaseline-plan.md),
[commons history](../commons-upgrade-plan.md),
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
| `E6-consumer-reuse` | Reconcile remaining redaction/SSE work and on-demand follow-ups; feature files only for genuinely active work; no release assignment invented |
| `E7-azure-adapters` | Deferred; owner scheduling plus original gates are entry criteria |
| `E8-django-scope-and-auth` | Deferred design review; explicit question whether a pre-release disposition is required |
| `E9-release-readiness` | Unreleased package matrix, installability evidence, CI gaps and kiln handoff; concrete acceptance stories, no release execution authorization |
| `E10-documentation-refactor` | This handoff's execution; completion means content/link/build checks pass, not that packages shipped |
| `E11-framework-codegen` | Deferred; existing import fences are not implemented generators; kiln ownership and entry criteria explicit |

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
| Q4 | Is R6/auth merely deferred, or must its disposition be decided before release? | **Unresolved release gate.** Record “owner must decide” in E8/E9; do not split packages or declare release readiness |
| Q5 | Does the first coordinated batch include all seven current workspace packages? | **Recommend all seven, including SQLAlchemy.** Matrix is a proposed scope until confirmed; unresolved CI coverage is not evidence of exclusion |
| Q6 | Should model conventions require SQLAlchemy status/natural keys/soft delete? | **Document only implemented guarantees; classify the rest as advice or unresolved design.** Any stronger requirement needs a separate feature decision |
| Q7 | What should become of the SAML-to-JWT follow-up note? | **Carry verbatim into deferred auth review.** Do not resolve auth design during document restructuring |
| Q8 | Preserve every old published page URL, or migrate links once? | **Update internal links and retain only known external handoff paths.** Add a redirect/tombstone only for a confirmed external consumer; no redirect dependency by default |

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
   stories own task state; epic/board summaries point to it.
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
- Package strict build results: pending completion of the review's independent
  package-site checks; replace this line before delivering the report.
- Local manifests, workspace membership, nav entries, CI invocations and tag list
  inspected. Remote releases, deployment state and fresh runtime test results
  were not checked; no release-readiness claim is made.
- No refactor, dependency installation, commit, push or release performed.
