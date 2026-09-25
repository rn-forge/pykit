# Plan context and migration ledger

This page maps the existing root documentation and plan sections to their intended homes. It is for maintainers reconciling the documentation; source plans remain historical evidence.

**Status:** done

**Owner:** pykit documentation refactor (E10).

**Source baseline:** local working tree, 2026-09-23; HEAD `12da7f3749a9f28518efe02c74a5f5709041cb3e`.

All five documentation batches completed in this working tree on 2026-09-24. The four owner questions and separate release-readiness work remain open in their owning records.

## Baseline inventory

`git status --short --untracked-files=all` was empty before this page was created. The baseline therefore includes the current disk contents without overwriting another task. Source hashes below are SHA-256 of those bytes. Historical files remain in place in Batch 1.

- Root `docs/`: 16 Markdown files, including 13 plan/review files.
- Package `docs/`: 148 Markdown files across seven independently built sites: commons 40, cli 9, tooling 11, web 26, django 40, fastapi 14, sqlalchemy 8.
- Seven package READMEs, seven package MkDocs configurations, and three web adoption Python examples remain in place.

| Source path | SHA-256 at baseline |
| --- | --- |
| `docs/01-extraction-from-cims.md` | `c7b559004facef2c5626e8e59e7b4f74c503274f55064591cb7aa769ed2e956e` |
| `docs/auth-overview.md` | `451400eeb4aa06385d9c76460c0e6548339fdb1e402a1984b584315d3e12bc11` |
| `docs/index.md` | `0440065a30b69f7bcba2e48118928b16093a0d05cfe7b8b543ce833fa85b03f8` |
| `docs/plans/README.md` | `0bc830ebb58ecb4e01c0875bf630d18bae28bd8ab65409421e68bd95555e15cd` |
| `docs/plans/azure-library-plan.md` | `5647070ffa1d7921e1ac2d31d62691846d21c9f5b647fd73559e3e3af3c7a471` |
| `docs/plans/cli-lifecycle-namespace-plan.md` | `25833c027740e5bb797773804fe32b7c04476adf217440e9cb3e19b1679ec0db` |
| `docs/plans/cli-lifecycle-retirement-plan.md` | `d2ff892b55adcc4a4f75974f704f378cc5db2e9989dc9a23cdace0039670cc6c` |
| `docs/plans/commons-upgrade-plan.md` | `afaeb0c039472589292787757470bec43d7f996dacd61aeb7c50087ea012f45c` |
| `docs/plans/django-upgrade-plan.md` | `cf5ac3c71d0a746a7824879fc5407b795a1421322e7004586c834032234c1475` |
| `docs/plans/fastapi-app-layer-plan.md` | `ea3d01256a56cb3b37944830373dfec4a384d22ecb7b7018f469b73332d45a26` |
| `docs/plans/fastapi-library-plan.md` | `095541c8df6b0897a1d417f389e4408962a67e159a57c1cb7e1c139f1703e910` |
| `docs/plans/kiln-dependencies.md` | `2d7674a4474d526fc2a1103d14490a13c4fa776f7bba7d6aed04f44e89d34a8b` |
| `docs/plans/standards-rebaseline-plan.md` | `b7757f7c00bf73befec0fe9bc6d3661bf2e36edeb12cc1cb122c7bfa61b6b3a1` |
| `docs/plans/web-api-reuse-plan.md` | `0a478ccb42726d9ae3f3ae4a5aa9a17f965c08e7ff5205aeb3f987c4b1aa70c5` |
| `docs/plans/web-library-plan.md` | `92fc04c0ddcceb14d5fe82a1e00abcda63e35514f344e2ffc58c713b2fc1bed3` |
| `docs/plans/reviews/docs-structure-review.md` | `f9f09c02404ac8ff8893d02a89dbcb48237d041cb601b69f058cfaa879dd7c65` |

## How to read the map

Destinations name current documentation homes. `done` means implemented or a decision settled; it does not mean a new release tag exists. Evidence dates are historical unless a current tree or commit is named. `E` and `F` IDs are pykit spec IDs; old Phase, D, R and AIP IDs remain searchable here.

Owner answers fix Q1–Q3 and Q6–Q8 to the review recommendations. Q4, Q5, Q9 and Q10 remain open. In particular, the Django split must be decided before tags, but its outcome is undecided; the seven-package release matrix is proposed, not approved.

## Disposition ledger

| Old path | Heading / ID | Classification | Destination | Current disposition | Evidence / date | Unresolved conflict |
| --- | --- | --- | --- | --- | --- | --- |
| `docs/index.md` | Package entry point | current page | `docs/index.md`; `docs/architecture/workspace.md` | Rewritten as a concise entry with seven package links in Batch 2. | Seven manifests and sites, 2026-09-23. | Baseline described removed correlation middleware and FastAPI wire-model mirrors. |
| `docs/auth-overview.md` | The three layers; framework support; shared OIDC authenticator | current explanation | `docs/architecture/authentication.md`; package auth guides | Split by audience in Batch 2; old path is a forwarding page. | Source and package guides, 2026-09-23. | Baseline installation example used an unpinned package name. |
| `docs/auth-overview.md` | Is bearer/basic the whole picture? | current explanation / scope | `docs/architecture/authentication.md`; `E8` | Keep implemented scope and explicitly deferred auth review separate. | Source, 2026-09-23. | Q4 remains open on scope decision. |
| `docs/auth-overview.md` | Steps for a new app: Django; FastAPI | current usage | Existing Django auth and FastAPI wiring guides | Verify instructions before merging in Batch 2. | Source, 2026-09-23. | Bare `uv add` command conflicts with pinned git installation. |
| `docs/auth-overview.md` | My followup thoughts | open owner note | `E8/F8.2` | Carry the original SAML-to-JWT sentence verbatim; do not decide the auth design (Q7 default). | Source, 2026-09-23. | Auth design remains open. |
| `docs/01-extraction-from-cims.md` | Superseded banner; Summary; Design decisions | historical-only | `docs/plans/archive/01-extraction-from-cims.md`; `docs/plans/context.md` | Preserve the original survey and its explicit supersession. | Survey 2026-07-22; supersession 2026-08-31. | Its Python 3.12 prerequisite and tier priorities are obsolete. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.1 RFC 7807 problem handler | superseded design | `E2`; `E3`; `E4` | Current shared RFC 9457 problem contract and adapter bindings replace this opt-in DRF proposal. | Web/adapter plans, 2026-09-23. | Original destination and wire details differ. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.2 pagination | superseded design | `E2`; `E3`; `E4` | Current AIP-158 cursor contract replaces page-number proposal. | Web plan; re-baseline R8, 2026-09-23. | Original pagination scheme differs. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.3 idempotency | superseded design | `E2`; `E4` | Shared store protocol and runner replace Django cache helper proposal. | Web plan; R2.5, 2026-09-22. | Original cache scope and status behavior differ. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.4 optimistic concurrency | superseded design | `E2`; `E3`; `E4` | Web precondition contract and framework adapters supersede the old request/body helper. | Web, Django and re-baseline plans, 2026-09-23. | Original 409 and weak ETag proposal is not the current wire contract. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.5 OmitEmptyMixin | historical-only | `E3`; archive | Implemented later by Django Phase 5; old survey placement is historical. | Supersession banner; Django plan, 2026-09-23. | Django Phase 5 delivery is condensed into the E3 done row in the review. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.6 PermissionByMethodMixin | historical-only | `E3`; archive | Implemented later by Django Phase 5; old survey placement is historical. | Supersession banner; Django plan, 2026-09-23. | Django Phase 5 delivery is condensed into the E3 done row in the review. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.7 production settings guards | implemented / revised | `E1`; commons guides | Commons environment guards supersede original helper names. | Commons Phase 7, 2026-09-09. | Original names may differ from current exports. |
| `docs/01-extraction-from-cims.md` | Tier 1: 1.8 readiness view | implemented / revised | `E2`; `E3`; `E4` | Current readiness contract and adapters supersede factory proposal. | Web/Django plans; R2.5, 2026-09-22. | Original soft-fail shape differs. |
| `docs/01-extraction-from-cims.md` | Tier 2: 2.1 resilience | implemented / revised | `E1` | Commons async resilience uses selected libraries, not the original `pybreaker`/`tenacity` proposal. | Commons Phase 8; board step 11, 2026-09-23. | Original dependencies and synchronous design differ. |
| `docs/01-extraction-from-cims.md` | Tier 2: 2.2 sequence generator | implemented / revised | `E3` | Django sequence implementation is covered by Django Phase 8. | Django plan, 2026-09-12. | — |
| `docs/01-extraction-from-cims.md` | Tier 2: 2.3 CloudEvents envelope | deferred | `E13` | Wait for the outbox/inbox subsystem need. | Commons deferred list; review register, 2026-09-23. | — |
| `docs/01-extraction-from-cims.md` | Tier 2: 2.4 request-ID middleware | superseded | `E4` considered and rejected | W3C Trace Context replaces the proposed custom request ID. | R3/R10, 2026-09-23. | Old request-ID mechanism must not return as open work. |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.1 OIDC/JWKS bearer auth | implemented / revised | `E2`; `E3`; `E8/F8.2` | Shared verifier and web authenticator plus framework bindings exist; whole-auth review remains deferred. | Web §10 and Django auth, 2026-09-15. | Original Django-only placement superseded. |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.2 outbox/inbox | implemented / revised | `E1`; `E3` | Commons protocol and Django messaging delivery replace original monolithic proposal. | Commons 8b; Django Phase 10, 2026-09-12. | Cloud-specific adapters remain deferred. |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.3 Celery | implemented | `E3` | Django Celery extra delivered. | Django Phase 11, 2026-09-12. | Optional relay wrapper was never a committed scope item. |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.4 claim check | deferred | `E13` | Second storage backend is entry criterion. | Commons deferred list; review register. | — |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.5 drf-spectacular/camelCase recipes | implemented / revised | Django package guides; `E3`; `E4` | Current framework guide owns setup; old recipe is historical. | Django guides and R1, 2026-09-23. | Original nested-dict escape hatch remains an uncommitted survey idea, not a registered feature. |
| `docs/01-extraction-from-cims.md` | Tier 3: 3.6 structlog compatibility | superseded | `E1`; commons logging guide | Commons StructLogger was built after this recommendation. | Commons Phase 9 gate, 2026-09-07. | Original “do not add structlog” decision is obsolete. |
| `docs/01-extraction-from-cims.md` | Deliberately not extracted; Implementation notes | historical-only | Archive; `docs/plans/context.md` | Consumer-specific code, Azure adapters and old execution instructions stay history. | Supersession banner, 2026-08-31. | — |
| `docs/plans/README.md` | Introduction; The documents; Execution order | current status / history | `docs/specs/index.md`; `docs/plans/index.md` | New board owns live status; old board is `plans/archive/plan-board.md`. | Review second pass, 2026-09-23. | Header says updated 2026-09-19 but includes 2026-09-23; several statuses say uncommitted after commits. |
| `docs/plans/README.md` | Dependency direction | current architecture | `docs/architecture/workspace.md`; `ADR-0001` | Verify graph against manifests and `.importlinter` during Batch 2. | Seven manifests, 2026-09-23. | Old prose counts fewer packages/contracts in other entry points. |
| `docs/plans/README.md` | Gated decisions | mixed done / deferred | `E1`–`E4`; `E7`; `E8`; context | Retain each gate outcome and Azure's unresolved gates; map reverse cursor to rejected. | Board, 2026-09-23. | FastAPI Phase 5 gate cites removed middleware. |
| `docs/plans/README.md` | What is open: backlog | mixed planned / deferred | `E8`; `E12`; `E13` | Split requires an owner decision before tags; auth and on-demand work remain deferred; kiln items stay kiln-owned. | Board, 2026-09-23. | Q4, Q9 and Q10 unresolved. |
| `docs/plans/README.md` | Standards re-baseline | mixed done / deferred | `E4`; `E8`; `E13` | Use later source and commits for R status, retaining rejected choices. | Commit log through 2026-09-23. | Calls R3/R4/R9/R10 uncommitted; R8 source also lists built Operation as leftover. |
| `docs/plans/README.md` | Conformance flake fix | done / historical validation | `E4`; context | Global response-propagator reset fixed; 25 historical full runs passed. | Board, 2026-09-23; seed `1707347094`. | Historical pass is not fresh validation. |
| `docs/plans/README.md` | Web API consumer reuse | mixed | `E3`; `E4`; `E6` | Only redaction and SSE remain planned; withdrawn and delivered phases are history. | Review second pass, 2026-09-23. | Board says Phase 5 is in working tree and Phase 6 remains planned. |
| `docs/plans/README.md` | pykit close-out | done / superseded | `E1`; `E2`; `E4`; `E5` | Record implementation and later supersession without a release claim. | 2026-09-15 through 2026-09-23 commits. | `Page<Item>` and StrictDataclassMixin references describe removed designs. |
| `docs/plans/README.md` | Last: the release | planned / owner gate | `E9`; `docs/releases/release-1/index.md`; release runbook | First coordinated batch scope awaits Q5 and tag approval. | Seven manifests; review F2, 2026-09-23. | Six-package order omits SQLAlchemy; actual workflow tags on main push. |
| `docs/plans/README.md` | Downstream acceptance | kiln-owned deferred | `E11`; `E12` | Golden repos, generator work and re-seed stay with kiln. | Board and review, 2026-09-23. | Current kiln E7 omits SQLAlchemy; Q10 open. |
| `docs/plans/README.md` | Standing rules | current decisions / historical mechanics | `ADR-0001`–`ADR-0006`; root guides/runbooks | Extract current principles once; retain old kiln timing as history. | README, manifests and review, 2026-09-23. | Claims generated kiln config/Taskfile flows that do not yet exist here. |
| `docs/plans/reviews/docs-structure-review.md` | Findings F1–F8; What is done; register; closed items | review evidence / current task source | `E10`; `docs/plans/context.md` | Preserve at current path; record its dispositions and conflicts in this ledger. | Review 2026-09-23. | Review register omits additional explicit plan items listed below. |
| `docs/plans/reviews/docs-structure-review.md` | Q1 taxonomy | decided default | `E10`; `ADR-0007` | Adopt root taxonomy now; keep manual MkDocs navigation. | Owner answer, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Q2 archive publication | decided default | `E10`; context | Keep raw archives repository-only; publish history index/context. | Owner answer, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Q3 package paths | decided default | `E10`; package docs | Keep package `api/` and web `adoption/` paths. | Owner answer, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Q6 model conventions | decided default | `E4`; web adoption guide | State implemented guarantees only; leave stronger ORM policy unresolved. | Owner answer, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Q7 SAML note | decided default | `E8/F8.2` | Carry owner note verbatim into deferred auth review. | Owner answer, 2026-09-23. | Auth design remains open. |
| `docs/plans/reviews/docs-structure-review.md` | Q8 links | decided default | `E10`; context | Update internal links; retain only known external handoff paths. | Owner answer, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Q4 Django split | open question | `E8/F8.1` | Split outcome remains open; decision precedes tags. | Owner answer, 2026-09-23. | Q4 open. |
| `docs/plans/reviews/docs-structure-review.md` | Q5 release scope | open question | `E9/F9.4` | Seven-package matrix is proposed only. | Owner answer, 2026-09-23. | Q5 open. |
| `docs/plans/reviews/docs-structure-review.md` | Q10 kiln tag order | open question | `E12` | Record conditional downstream correction; do not edit kiln. | Owner answer, 2026-09-23. | Q10 open; depends on Q5. |
| `docs/plans/reviews/docs-structure-review.md` | Batch 1–5 | documentation work | `E10/F10.1`–`F10.5` | Batches 1–3 executed in this working tree; Batches 4–5 remain planned. | Review instructions, 2026-09-23. | — |
| `docs/plans/commons-upgrade-plan.md` | Execution status; Parts A–C | history | `plans/context.md`; E1 | Implemented; first two-layer boundary superseded by Part D | `28bef7f`, `4624bfe`, 2026-09-09 | Status text dates Parts A–F before F commit date |
| `docs/plans/commons-upgrade-plan.md` | Final package boundary | superseded decision | ADR-0001; E1; `plans/context.md` | Three-layer D/E boundary supersedes this two-layer proposal; one-way graph and no-shim rule survive | Part D, `f59c40f`, 2026-09-12 | Historical graph lacks current SQLAlchemy |
| `docs/plans/commons-upgrade-plan.md` | Framework code generators | deferred; kiln-owned command surface | E11; E12; ADR-0006 | Import fences exist; framework providers and kiln commands await kiln work | Plan; review 2026-09-23 | — |
| `docs/plans/commons-upgrade-plan.md` | Guiding principle; conventions; deliberately not changed | decision and rejected alternatives | ADR-0001; ADR-0006; `plans/context.md` | Keep current boundary and extras rules; `DictUtils.get/set/compare`, existing thin wrappers, serialization left intact | Plan; current README / `.importlinter` | Some old text calls strict-by-default dataclasses permissive |
| `docs/plans/commons-upgrade-plan.md` | Phase 0 | implemented | E1 | Reflection, boolean parsing, JSON logging declaration, exception syntax fixes | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 1 | implemented | E1; commons logging guide | Rich replaced coloredlogs | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 2 | implemented, later relocated | E1; commons console guide | `AppConsole` lives in commons after E.2 | `28bef7f`; `f59c40f` | Original tooling placement superseded |
| `docs/plans/commons-upgrade-plan.md` | Phase 3 | implemented, later reshaped | E1; cli guide | Typer layer lives in cli; `build_app` replaced by `CliApp` | `28bef7f`; `f59c40f` | Original builder superseded |
| `docs/plans/commons-upgrade-plan.md` | Phase 4 | implemented, later tightened | E1; commons dataclasses guide | dacite deserialization; E.1a made strict default | `28bef7f`; `f59c40f` | Original permissive default superseded |
| `docs/plans/commons-upgrade-plan.md` | Phase 5.1 | rejected/superseded | E1 considered and rejected; `plans/context.md` | `mergedeep` skipped; Phase 14 kept deep-copy merge and added layers/provenance | Plan 2026-09-04 | Missing explicit closed-item row |
| `docs/plans/commons-upgrade-plan.md` | Phase 5.2 | implemented | E1 | `pkgutil.resolve_name` for absolute imports, preserve relative import behavior | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 5.3 | superseded by Phase 10 | E1; `plans/context.md` | Atomic-write design reconciled with both donor repos in Phase 10 | Plan 2026-09-04 | Missing explicit closed-item row |
| `docs/plans/commons-upgrade-plan.md` | Phase 6; 6.1–6.3 | rejected at gate | E1 considered and rejected | OmegaConf resolver abandoned; existing resolver retained | 2026-09-07 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 7 | implemented | E1 | Environment fail-fast guards | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 8; 8.1–8.4 | implemented | E1 | Resilience client/circuit breaker behind extra | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 8b | implemented | E1 | Messaging protocol and in-memory implementation | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 8c | implemented | E1 | Secret-store protocol and environment implementation | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 8d | implemented | E1 | Object-store protocols | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 9; 9.1–9.5 | implemented after passing gate | E1; commons logging guide | Optional `StructLogger` front end | Gate 2026-09-07; `28bef7f` | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 10 | implemented | E1 | Atomic write reconciled across donor repos | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 11; 11.1–11.3 | implemented | E1; commons documents guide | TOML/YAML/JSON document helpers | `28bef7f`, 2026-09-09 | Early optional-dependency design superseded by 11.4 |
| `docs/plans/commons-upgrade-plan.md` | Phase 11.4 | superseded design | E1; `plans/context.md` | Single ruamel YAML backend; `documents` extra removed; base document dependencies | Plan; `28bef7f`, 2026-09-09 | Missing explicit closed-item row |
| `docs/plans/commons-upgrade-plan.md` | Phase 12; 12.1–12.4 | implemented; scope exclusion | E1; ADR-0001 | Commons hashing and tooling state; backups explicitly outside StateStore | `28bef7f` / `4624bfe`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 13 | implemented | E1 | Root discovery and path containment | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 14 | implemented | E1 | Layered merge/provenance; replaces Phase 5.1 | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 15 | implemented | E1 | Flatten and unified diff | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 16 | implemented | E1 | Tooling Jinja template engine | `4624bfe`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 17 | implemented | E1 | Generic entry-point discovery in commons | `28bef7f`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 18; 18.1–18.2 | implemented | E1 | Tooling installer mechanics; product policy remains local | `4624bfe`, 2026-09-09 | — |
| `docs/plans/commons-upgrade-plan.md` | Phase 18.3 | withdrawn alternative | ADR-0001; `plans/context.md` | `Environment.rnf_home()` withdrawn; workstation home convention stays out of commons | Part C | Missing explicit closed-item row |
| `docs/plans/commons-upgrade-plan.md` | Phase 18.4 | deferred extension | E13 | `ProductInstaller` shared contract waits for second product | Part C; review 2026-09-23 | — |
| `docs/plans/commons-upgrade-plan.md` | What Part C leaves in applications | explicit out of scope | ADR-0001; `plans/context.md` | Domain models, result envelopes, BaseCommand, resolution policy, validators, doctor stay local | Part C | Do not promote as pykit work |
| `docs/plans/commons-upgrade-plan.md` | D.0 | historical sequencing | E1; `plans/context.md` | Defects preceded package moves | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | D.1 (F1–F6) | implemented | E1 | Generation, byte preservation, rollback, enum, path, stale-drift fixes | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | D.2 (D52) | implemented; layout later superseded | E1; ADR-0001 | Three-layer split, no compatibility re-exports | `f59c40f`, 2026-09-12 | Its cli module layout superseded by Part E |
| `docs/plans/commons-upgrade-plan.md` | D.3 (A2) | implemented | E1; ADR-0007 | Tooling retains docs mechanics; caller supplies policy | `f59c40f`, 2026-09-12 | Original plan says kiln fixture supplies default; verify current consumer before current-doc claim |
| `docs/plans/commons-upgrade-plan.md` | D.4 (D55) | implemented; cli layout later superseded | E1; ADR-0001 | Grouped modules; public names remain | `f59c40f`, 2026-09-12 | Part E adjusts cli layout |
| `docs/plans/commons-upgrade-plan.md` | D.5 (F10–F14) | implemented | E1 | CLI output, docs YAML/anchors/results, AGENTS pointer | `f59c40f`, 2026-09-12 | F14 needed no edit; AGENTS was already pointer |
| `docs/plans/commons-upgrade-plan.md` | D.6 (F7) | implemented | E1 | CLI/tooling CI and import gate | `f59c40f`, 2026-09-12 | Current SQLAlchemy CI omission is separate F9.1 |
| `docs/plans/commons-upgrade-plan.md` | D.7 (F9) | implemented locally | E1; ADR-0002 | Pinned git URL contract and local built-distribution smoke test | `f59c40f`, 2026-09-12 | No tag-based external installability yet; F9.5 remains open |
| `docs/plans/commons-upgrade-plan.md` | D.8 | planned release work | E9; `releases/release-1/index.md` | Tag cut awaits owner and kiln E7 trigger | Review 2026-09-23: no new tags | Old order omits SQLAlchemy; Q5 remains open |
| `docs/plans/commons-upgrade-plan.md` | D.9 | kiln-owned acceptance | E12 | `golden/python-app` must prove declaration-only CLI | Kiln acceptance; review 2026-09-23 | Do not mark pykit implementation open |
| `docs/plans/commons-upgrade-plan.md` | E.0 | historical findings | E1; `plans/context.md` | Five CLI shape findings and two defects fixed | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | E.1 | superseded implementation | E1; `plans/context.md` | `StrictDataclassMixin` class removed by E.1a | E.1a 2026-09-15 | Missing explicit closed-item row |
| `docs/plans/commons-upgrade-plan.md` | E.2 | implemented | E1; ADR-0001 | AppConsole moved to commons runtime | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | E.3 | implemented | E1; cli guide | `CliApp` replaces `build_app` and declaration helpers | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | E.4 | implemented removals | E1; `plans/context.md` | Removed option callbacks and parse_key_values; SetOption remains | `f59c40f`, 2026-09-12 | — |
| `docs/plans/commons-upgrade-plan.md` | E.1a | implemented | E1; commons dataclasses guide | Strict DataclassMixin default; LenientDataclassMixin opt-out | 2026-09-15; committed by `231a68e` review mapping | — |
| `docs/plans/commons-upgrade-plan.md` | F | implemented mechanics; CLI surface superseded | E5; ADR-0005 | Installer mechanics survive; `[cli.lifecycle]` moved to tooling-owned sibling `[lifecycle]` | `757908e`, 2026-09-14; `1a8241b`, 2026-09-22 | Part F still calls the removed CLI table done/current |
| `docs/plans/commons-upgrade-plan.md` | G | implemented | E1; E12 for kiln F4.2 | Optional pydantic StrictModel; kiln config-manager adoption downstream | `231a68e`, 2026-09-16 | Source says only working-tree done; review says committed |
| `docs/plans/commons-upgrade-plan.md` | Deferred: CloudEvents | deferred | E13 | Envelope helper only with outbox/inbox consumer | Plan; review register 2026-09-23 | — |
| `docs/plans/commons-upgrade-plan.md` | Deferred: claim-check | deferred | E13 | Wait for second storage backend | Plan; review register 2026-09-23 | — |
| `docs/plans/commons-upgrade-plan.md` | Not in this plan: agentkit/taskkit | external consumer scope | E12; `plans/context.md` | Donor mapping and future consumer use, not pykit implementation | Plan | Retired taskkit cannot be assigned new work |
| `docs/plans/commons-upgrade-plan.md` | Not in this plan: Django-shaped cims inventory | historical scope exclusion | E3/E4/E8/E13; `plans/context.md` | Later Django/web plans decide these items; do not re-open from old list | Plan; current review | Several named old cims ideas lack individual register/closed rows; classify historical-only unless a later plan owns them |
| `docs/plans/cli-lifecycle-namespace-plan.md` | Entire plan; Problem; original Decision | superseded | E5; ADR-0005; `plans/context.md` | Namespace design survives, but CLI-owned `[cli.lifecycle]` design retired | Superseded 2026-09-21; retirement `1a8241b`, 2026-09-22 | Old original status says planned; top says superseded |
| `docs/plans/cli-lifecycle-namespace-plan.md` | Changes; Tests; Validation; Acceptance | historical-only | E5; `plans/context.md` | Obsolete CLI implementation and tests; final behavior covered in tooling | Retirement `1a8241b` | Must not resurrect removed CLI records/methods |
| `docs/plans/cli-lifecycle-namespace-plan.md` | Handoff to kiln | kiln-owned; superseded path | E12; `plans/context.md` | Kiln template must use tooling `build_tool_app` and sibling `[lifecycle]`; namespace self still desired | Retirement plan Handoff, 2026-09-21 | Old handoff asks for `[cli.lifecycle]` and direct namespace-only update |
| `docs/plans/cli-lifecycle-retirement-plan.md` | Problem | historical rationale | E5; ADR-0005 | Generic CLI boundary; lifecycle vocabulary belongs to tooling | Owner decision 2026-09-21; `1a8241b` | — |
| `docs/plans/cli-lifecycle-retirement-plan.md` | Decision | implemented | E5; ADR-0005; tooling lifecycle guide | Sibling `[lifecycle]`; `LifecycleSurface` and `build_tool_app` owned by tooling; `target` removed | `1a8241b`, 2026-09-22 | Supersedes Part F and namespace plan current-state text |
| `docs/plans/cli-lifecycle-retirement-plan.md` | Changes made | implemented | E5; `plans/context.md` | Removed CLI lifecycle APIs; rebuilt tooling implementation, docs and tests | `1a8241b`, 2026-09-22 | — |
| `docs/plans/cli-lifecycle-retirement-plan.md` | Validation | dated evidence | E5; `plans/context.md` | Source reports tests/lint/types/docs passed at implementation | Plan 2026-09-21; `1a8241b` | Historical result is not a fresh Batch 1 test pass |
| `docs/plans/cli-lifecycle-retirement-plan.md` | Handoff to kiln | kiln-owned | E12 | Generator template, config and golden repo move to `build_tool_app` plus `[lifecycle]` | Plan 2026-09-21 | Review register covers golden tool but not each template/config migration substep |
| `docs/plans/kiln-dependencies.md` | §1 Phase A | historical completed handoff | E1; `plans/context.md` | Commons stabilization | `28bef7f`, 2026-09-09 | — |
| `docs/plans/kiln-dependencies.md` | §1 Phase C | historical completed handoff | E1; `plans/context.md` | First two-layer extraction later corrected | `4624bfe`, 2026-09-09 | — |
| `docs/plans/kiln-dependencies.md` | §1 Phase C.2 (F1–F14; D52/D55/A2) | implemented handoff | E1; ADR-0001/0002 | Defects, split, policy, layout, CI, release contract and pointer | `f59c40f`, 2026-09-12 | Historic package layout later corrected by Part E |
| `docs/plans/kiln-dependencies.md` | §2.1 Phase C.3 | implemented, then surface retired | E5; ADR-0005 | Installer remains; `[cli.lifecycle]` design superseded by `[lifecycle]` | `757908e`; `1a8241b` | Heading says Open though also done; old table and `target` no longer current |
| `docs/plans/kiln-dependencies.md` | §2.1a kiln F4.2 | pykit implemented; kiln-owned acceptance | E1; E12 | StrictModel in commons; kiln config manager adoption deferred downstream | `231a68e`, 2026-09-16 | Handoff says done in working tree, now committed |
| `docs/plans/kiln-dependencies.md` | §2.2 FastAPI; Phase 8 | pykit implemented; kiln-owned acceptance | E3; E12 | Adapter committed; golden/python-web-api acceptance belongs to kiln | `3e80dbd`; review 2026-09-23 | — |
| `docs/plans/kiln-dependencies.md` | §2.3 Releases; kiln E7 | planned trigger; kiln-owned pin flip | E9; E12; `releases/release-1/index.md` | Owner declaration of stability triggers release coordination; scope Q5 unresolved | Review 2026-09-23 | Tag order omits SQLAlchemy; no release occurred |
| `docs/plans/kiln-dependencies.md` | §3.1 D52 boundary | historical decision | ADR-0001; E1 | Current three-layer boundaries; Part E moves console to commons | `f59c40f`, 2026-09-12 | Table's first row has original CLI placement, qualifying parenthetical only |
| `docs/plans/kiln-dependencies.md` | §3.1 D37 codegen | deferred; kiln-owned command surface | E11; E12; ADR-0006 | Fences exist; generators do not | Review 2026-09-23 | — |
| `docs/plans/kiln-dependencies.md` | §3.2 D55 package layout | historical decision | ADR-0001; E1; `plans/context.md` | Layout record; Part E and lifecycle retirement determine current CLI/tooling homes | `f59c40f`; `1a8241b` | Its lifecycle layout and CLI count may be stale |
| `docs/plans/web-library-plan.md` | Survey of CIMS/IntelliBench; guiding principle | historical evidence | `plans/context.md`; E2 | Prior art, not consumer compatibility requirements | survey 2026-07-22/08-31 | — |
| `docs/plans/web-library-plan.md` | Alignment 1, D52: runtime/tooling boundary | architecture decision | ADR-0001; `architecture/workspace.md` | Keep actual package graph; SQLAlchemy now present | plan 2026-09-10; R9 2026-09-23 | Old graph omits SQLAlchemy |
| `docs/plans/web-library-plan.md` | Alignment 2: import-linter | architecture decision | ADR-0001; E2 | Preserve executable boundary, verify actual `.importlinter` | plan 2026-09-10 | — |
| `docs/plans/web-library-plan.md` | Alignment 3, D46: pinned git tags | release decision | ADR-0002; E9; release runbook | Pinned direct URLs are declared; proposed tags remain uncut | plan 2026-09-10; review 2026-09-23 | Historical checklist marks pin done but release tag is absent |
| `docs/plans/web-library-plan.md` | Alignment 4, D55: flat layout | architecture decision | ADR-0001; E2 | Historical rationale; current module layout belongs in package docs | plan 2026-09-10 | — |
| `docs/plans/web-library-plan.md` | Alignment 5, D53: golden consumers | downstream acceptance | E12 | Kiln owns golden repos, not pykit implementation | plan 2026-09-10 | — |
| `docs/plans/web-library-plan.md` | Alignment 6: repo shape, kiln F.1 | downstream handoff | E12 | Kiln config/state re-seed waits on kiln | plan 2026-09-10 | — |
| `docs/plans/web-library-plan.md` | Alignment 7: validation | historical evidence | E2; `plans/context.md` | Dated commands; no fresh pass inferred | plan 2026-09-10 | — |
| `docs/plans/web-library-plan.md` | Phase 0 / 0.1 / 0.3: scaffold, Python floor, repo integration | implemented feature | E2; package README | Built and committed; Python >=3.14 remains | status 2026-09-11; commit `8b5160b` | Checklist says no commit/push, superseded by status |
| `docs/plans/web-library-plan.md` | Phase 0.2: `asgi-correlation-id` and `rfc9457` | rejected alternatives | E2 Considered and rejected; context | Both rejected; no optional ASGI dependency | decision 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Phase 1: `context.py` | superseded feature | E2; E4/R3 | Originally implemented, removed with W3C Trace Context | `8b5160b`; R3 2026-09-22 | Plan status says all phases applied, but this symbol was later removed |
| `docs/plans/web-library-plan.md` | Phase 2 / 2.1–2.5: problem format and registry | implemented feature | E2; web problem docs | Built; current contract lives in web docs/source | `8b5160b`; implementation note 2026-09-11 | Original `str(exc)` detail rule corrected to `.message` |
| `docs/plans/web-library-plan.md` | Phase 3 / 3.1–3.3: ETag and If-Match | implemented feature | E2; web concurrency docs | Built, 412 conflict rule | `8b5160b` | — |
| `docs/plans/web-library-plan.md` | Phase 4 / 4.1–4.3: AIP-158 cursors | implemented feature | E2; web pagination docs; E4/R8 | Built, later pagination decisions governed by R8 | `8b5160b`; R8 `9af1705` | Original reverse-cursor discussion is closed by forward-only choice |
| `docs/plans/web-library-plan.md` | Phase 5 / 5.1–5.2: idempotency protocol | implemented feature | E2; web idempotency docs | Sync and async memory stores split | `8b5160b`, 2026-09-11 | Original one-class protocol design corrected |
| `docs/plans/web-library-plan.md` | Phase 6: health aggregation | implemented feature | E2; web health docs | Built; per-check async timeout added later | `8b5160b`; 2026-09-13 update | — |
| `docs/plans/web-library-plan.md` | Phase 7: ASGI correlation middleware | superseded feature | E2; E4/R3 | Originally implemented, removed by Trace Context re-baseline | `8b5160b`; R3 2026-09-22 | Plan status/checklist calls it built; current source lacks it |
| `docs/plans/web-library-plan.md` | Phase 8: public API and docs | implemented feature | E2; package README/docs | Built; package docs remain consumer authority | `8b5160b` | — |
| `docs/plans/web-library-plan.md` | Phase 9 and §9.1: context pack/OpenAPI naming | implemented feature | E2; web adoption docs; E4/R1 | Context pack and naming built; `Page<Item>` naming later removed by R1 | `8b5160b`; 2026-09-15; R1 | Original naming rule superseded |
| `docs/plans/web-library-plan.md` | Phase 10 / 10.1–10.5: authentication contract | implemented feature | E2; web auth docs | Contract and OIDC authenticator built; auth redesign deferred in E8 | `8b5160b`; 2026-09-15 update | — |
| `docs/plans/web-library-plan.md` | Phase 11 / 11.1–11.3: conformance table | implemented feature | E2; web conformance docs | Built; framework drivers later added | `8b5160b`; 2026-09-13 update | — |
| `docs/plans/web-library-plan.md` | Unification boundary: common ORM/repository and serializer | rejected alternatives | ADR-0004; E2 Considered and rejected | No shared ORM base, repository API, or serializer abstraction | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Amendments A.1: Django phases | cross-plan supersession | E3; E4 | Django adapter ownership and status mappings; correlation header later removed | plan; R3/R4 | A.1's `X-Correlation-ID` no longer current |
| `docs/plans/web-library-plan.md` | Amendments A.2: commons secrets/messaging/objects/auth | implemented cross-plan work | E1/E2; commons docs | Historical dependency changes; verify current package API | plan; 2026-09-12 auth update | — |
| `docs/plans/web-library-plan.md` | Amendments A.3: resilience redesign | cross-plan decision | E1; context | Commons plan owns gate and resulting choice | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Deferred: FastAPI package | completed trigger | E3 | Trigger fired; package implemented | fastapi `3e80dbd` | Older deferral superseded |
| `docs/plans/web-library-plan.md` | Deferred: SQLAlchemy first cut | completed trigger / residual deferred | E4/R9; E13 | R9 unparked and built first cut; SQL idempotency/session/readiness remain deferred | R9 `653ac47`, 2026-09-23 | Older parked text conflicts with current package |
| `docs/plans/web-library-plan.md` | Deferred: multi-tenant row scoping | deferred feature | E13 | Wait for second application's tenancy model | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Deferred: LLM port / Azure OpenAI adapter | deferred feature | E7; context | Azure-owned candidate, owner schedule gate | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | FastAPI extraction candidates | historical inventory | E3; context | Adapter candidates mapped to FastAPI phases; pydantic mirrors later removed | survey 2026-08-31; R4 | Old `create_app` exclusion reversed by app layer, then FastApiApp |
| `docs/plans/web-library-plan.md` | Not in plan: CIMS/IntelliBench rewrites | consumer-owned exclusion | context | Work remains in consumer repositories | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Not in plan: lowering Python floor | historical-only exclusion | context | Separate workspace decision if a consumer needs it | plan 2026-09-11 | — |
| `docs/plans/web-library-plan.md` | Not in plan: resilience redesign | cross-plan exclusion | E1; context | Commons owns decision | plan 2026-09-11 | — |
| `docs/plans/web-api-reuse-plan.md` | Survey and library evaluations | historical evidence | context; E6 | `sse-starlette` evaluated, not installed; redaction candidates rejected; no new adoption authorization | 2026-09-19; review tree 2026-09-23 | Library section calls SSE adopted while current source/extra absent |
| `docs/plans/web-api-reuse-plan.md` | Findings 1–6, 13 | feature inventory | E3/E4/E6; context | Map each numbered finding to phases below | 2026-09-19 | Header says Phase 5 working tree, but R3 removed it |
| `docs/plans/web-api-reuse-plan.md` | Phase 0 / finding 13: FastApiApp | implemented feature | E3; fastapi app docs | Subclass replaces `create_app` | 2026-09-19; source `fastapi/app.py` | — |
| `docs/plans/web-api-reuse-plan.md` | Phase 0: fluent builder | rejected alternative | E3 Considered and rejected; context | No mutable builder API | 2026-09-19 | — |
| `docs/plans/web-api-reuse-plan.md` | Phase 1 / finding 1: OpenAPI component helpers | withdrawn feature | E4/R1; context | Implemented then removed by R1; no open task | R1 2026-09-21 | Reuse opening initially describes planned work |
| `docs/plans/web-api-reuse-plan.md` | Phase 2 / finding 2: log redaction | planned feature | F6.1 | Not built in commons source | review 2026-09-23; source check 2026-09-23 | — |
| `docs/plans/web-api-reuse-plan.md` | Phase 3 / finding 3: SSE | planned feature | F6.2 | Not built; owner approval needed before adding dependency | review 2026-09-23; no `sse.py` or extra | Earlier evaluation's “adopted” is design intent, not installed dependency |
| `docs/plans/web-api-reuse-plan.md` | Phase 3: hand-written SSE encoder and `web.sse` | rejected alternative | E6 Considered and rejected; context | Evaluation retired the earlier draft | evaluation 2026-09-19 | — |
| `docs/plans/web-api-reuse-plan.md` | Phase 4 / finding 4: problem extensions, unmapped exceptions | implemented feature | E2/E4; web problem docs | Built; source contains both APIs | source check 2026-09-23 | Plan opening's “working tree” status is stale against committed review state |
| `docs/plans/web-api-reuse-plan.md` | Phase 5 / finding 5: correlation ID validation | withdrawn feature | E4/R3; context | Removed with W3C Trace Context | R3 2026-09-22 | Opening status still says “working tree” |
| `docs/plans/web-api-reuse-plan.md` | Phase 6 / finding 6: CORS | superseded/done feature | E4/R2.5 B8; fastapi CORS docs | Delivered by broader R2.5 B8 | R2.5 `373d6bc`; source `fastapi/cors.py` | Opening re-baseline says “unchanged”, section says superseded |
| `docs/plans/web-api-reuse-plan.md` | Findings 7–12 | rejected alternatives | E6 Considered and rejected; context | Offset pagination, offload, SPA mount, serve, settings facade, port container rejected | findings 2026-09-19 | — |
| `docs/plans/web-api-reuse-plan.md` | Finding 11: Config vs pydantic-settings guidance | documentation-only output | commons config guide; E10 | Plan explicitly requests brief guidance despite rejecting facade | findings 2026-09-19 | Missing from review register/closed list as deliverable |
| `docs/plans/web-api-reuse-plan.md` | Adoption findings | consumer-owned evidence | context; E12 where kiln-owned | Consumer duplication is prior art; no pykit implementation assignment | survey 2026-09-19 | Some text still recommends withdrawn Phase 1 and `create_app` |
| `docs/plans/web-api-reuse-plan.md` | Consumer acceptance: Account Portal, IntelliBuild | deferred acceptance | E6 note | Parked until applications unpark | 2026-09-21 | Phase 0/1/4/5/6 acceptance table still reads as active |
| `docs/plans/web-api-reuse-plan.md` | Consumer acceptance: PhotoTidy and Apollo | downstream acceptance | F6.2 | Acceptance for SSE remains stated | 2026-09-21 | — |
| `docs/plans/fastapi-library-plan.md` | Alignment 1–4, D46/D52/D55 | architecture/release decisions | ADR-0001/0002; E3/E9 | Current graph and pin rules; old graph omits SQLAlchemy | 2026-09-12; R9 2026-09-23 | Phase 0 says release prerequisite, but package implemented before tag |
| `docs/plans/fastapi-library-plan.md` | Alignment 5, D37/D56: codegen | deferred feature | E11 | Fence exists; generators wait on kiln D2/D37 | plan 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Alignment 6, Phase 8: golden repo | kiln-owned acceptance | E12 | Kiln owns golden/python-web-api | plan 2026-09-12; review 2026-09-23 | — |
| `docs/plans/fastapi-library-plan.md` | Alignment 7: namespace collision | implemented decision | E3; package README | Kept `rn_forge.fastapi` namespace | status 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Phase 0 / 0.1–0.3: scaffold/boundaries/namespace | implemented feature | E3 | Built and committed; direct URL pin names uncut tag | `3e80dbd`; status 2026-09-12 | Checklist marks no commit, contradicted by status |
| `docs/plans/fastapi-library-plan.md` | Phase 1: exception handlers | implemented feature | E3; fastapi problem docs | Built | `3e80dbd` | — |
| `docs/plans/fastapi-library-plan.md` | Phase 2: pydantic mirrors | removed feature | E3; E4/R4 | Initially built, removed by R4 | `3e80dbd`; R4 `df7a245` | Original status/checklist says mirrors ship |
| `docs/plans/fastapi-library-plan.md` | Phase 3: OpenAPI repair | implemented/revised feature | E3; E4/R1 | Current adapter schema behavior follows R1 | `3e80dbd`; R1 `373d6bc` | Original injection mechanics superseded |
| `docs/plans/fastapi-library-plan.md` | Phase 4: header/query dependencies | implemented feature | E3; fastapi docs | Built; verify current API against R8 pagination | `3e80dbd`; R8 `9af1705` | — |
| `docs/plans/fastapi-library-plan.md` | Phase 5: correlation wiring | removed feature | E3; E4/R3 | Initially installed web middleware, removed with Trace Context | `3e80dbd`; R3 `630142c` | Original status/checklist says middleware active |
| `docs/plans/fastapi-library-plan.md` | Phase 6: health router | implemented feature | E3; fastapi health docs | Built; timeout support added 2026-09-13 | `3e80dbd`; dated update | — |
| `docs/plans/fastapi-library-plan.md` | Phase 6b: auth binding | implemented feature | E3; fastapi auth docs | Built | `3e80dbd`; 2026-09-13 update | Earlier status says commons auth absent, later paragraph says present |
| `docs/plans/fastapi-library-plan.md` | Phase 6c: conformance driver | implemented feature | E3 | Built; independent stack proof | `3e80dbd`; 2026-09-13 update | — |
| `docs/plans/fastapi-library-plan.md` | Phase 7: public API/docs | implemented feature | E3; package docs | Built | `3e80dbd` | — |
| `docs/plans/fastapi-library-plan.md` | Phase 8: golden/python-web-api | kiln-owned deferred acceptance | E12 | No new pykit implementation task; kiln trigger | review 2026-09-23 | Historical checklist remains unchecked |
| `docs/plans/fastapi-library-plan.md` | Deferred: codegen | deferred feature | E11 | Wait for kiln D2/D37 | plan 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Deferred: SQLAlchemy | completed trigger/residual deferred | E4/R9; E13 | First cut built by R9; remaining SQL store/session/readiness deferred | R9 `653ac47` | Parked wording is stale |
| `docs/plans/fastapi-library-plan.md` | Deferred: multi-tenant scope | deferred feature | E13 | Second app tenancy trigger | plan 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Deferred: OIDC/JWKS Security | completed feature | E3 Phase 6b | Shipped in original adapter work | `3e80dbd` | — |
| `docs/plans/fastapi-library-plan.md` | Deferred: SSE/WebSockets/background tasks | mixed scope | F6.2; context | SSE revived by reuse Phase 3; WebSockets/background tasks remain out of scope, no trigger | plan 2026-09-12; reuse 2026-09-19 | Older “no prior art” SSE claim superseded by later survey |
| `docs/plans/fastapi-library-plan.md` | Not in plan: IntelliBench/IntelliBuild rewrite | consumer-owned exclusion | context | Consumer repository work | plan 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Not in plan: web modules | package boundary | ADR-0004; context | Web owns framework-neutral contracts | plan 2026-09-12 | — |
| `docs/plans/fastapi-library-plan.md` | Not in plan: lowering Python floor | historical-only exclusion | context | Separate workspace gate if needed | plan 2026-09-12 | — |
| `docs/plans/fastapi-app-layer-plan.md` | Problem/decision, Scope, Implementation surface | superseded feature | E3; E4; fastapi app docs | `AppConfig` and factory implemented, then factory replaced by FastApiApp | 2026-09-18; reuse Phase 0 2026-09-19 | Header “implemented” is historical, not current factory contract |
| `docs/plans/fastapi-app-layer-plan.md` | Additional utility endpoints | explicit out-of-scope | context | Require their own future contract | 2026-09-18 | — |
| `docs/plans/fastapi-app-layer-plan.md` | Application-file generation/[codegen] | deferred external work | E11 | Kiln/framework codegen owns future bootstrap generation | 2026-09-18 | — |
| `docs/plans/fastapi-app-layer-plan.md` | Acceptance | historical validation | E3; context | Factory-era tests were dated evidence; current subclass needs separate evidence | 2026-09-18 | — |
| `docs/plans/fastapi-app-layer-plan.md` | Downstream handoff to kiln | downstream ownership | E12 | Kiln owns task/template/golden fixture update; no pykit shipping gate inferred | 2026-09-18 | — |
| `docs/plans/django-upgrade-plan.md` | Alignment §§1–8 (D46, D55, D37, D56) | historical decision | E3; ADR-0001/0002/0004 | Implemented boundary, dependency, layout and pinned tag design; release remains open | plan status 2026-09-12; review What is done | Old release steps omit SQLAlchemy; F9 tracks current matrix |
| `docs/plans/django-upgrade-plan.md` | Summary, conventions, dependencies | historical design | E3; Django package guides | Implemented; current usage stays with package | commit `9d8588c` per review | Original phase text differs from implementation status; status wins |
| `docs/plans/django-upgrade-plan.md` | Things deliberately not extracted: cims business modules and integration adapters | rejected scope | context | Consumer domain logic stays in cims | plan exclusions | None |
| `docs/plans/django-upgrade-plan.md` | Things deliberately not extracted: Azure adapters and management commands | downstream | E7; context | Azure work remains parked; consumer commands stay with consumer | plan exclusions; Azure header 2026-09-13 | None |
| `docs/plans/django-upgrade-plan.md` | Things deliberately not extracted: `AuditContextMiddleware` header trust | rejected | context closed item | Do not library-package a dev auth bypass | plan exclusions | None |
| `docs/plans/django-upgrade-plan.md` | Phase 0 test harness | done | E3 | Fixture and tests implemented | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 1 problem adapter | done | E3; Django exception guide | DRF problem adapter implemented; no web exception re-exports | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 2 pagination | done | E3; E4 R8 | Cursor pagination implemented, later expanded by orderBy; forward only | plan status 2026-09-12; R8 2026-09-23 | Earlier unique-first-field rule superseded by R8 id tiebreak |
| `docs/plans/django-upgrade-plan.md` | Phase 2 reverse cursor / `previousPageToken` | rejected | E3; context closed item | Forward-only decision | plan status 2026-09-12; review Closed items | None |
| `docs/plans/django-upgrade-plan.md` | Phase 3 cache idempotency | done | E3; Django DRF guide | Django cache adapter implemented | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 4 concurrency and immutability | done | E3; Django models guide | Versioned/immutable mixins and precondition delegation implemented | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 5 two mixins | done | E3; Django DRF guide | `OmitEmptyMixin`, `PermissionByMethodMixin` implemented | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 6 readiness and environment guard | done | E3; Django guide | Readiness factory and commons guard delegation implemented | plan status 2026-09-12; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 7 WSGI correlation middleware | superseded | E3 historical; E4 R3/R10.2 | Implemented then removed by R10.2 | plan status 2026-09-12; R10.2 status 2026-09-23 | Plan still describes removed middleware as current |
| `docs/plans/django-upgrade-plan.md` | Phase 8 sequence generator | done | E3; Django models guide | Abstract sequence model; consumer owns migration | plan status 2026-09-12; `9d8588c` | PostgreSQL local run is historical, not fresh validation |
| `docs/plans/django-upgrade-plan.md` | Phase 9 JWKS bearer auth | done | E3; Django auth guide | Initial binding later completed with commons JWKS and web OIDC | plan second pass 2026-09-13; `9d8588c` | Earlier “commons auth does not exist” paragraph superseded by later status |
| `docs/plans/django-upgrade-plan.md` | Phase 10 outbox/inbox gate | done; gate passed | E3; Django messaging guide | Owner approved; messaging implemented | plan second pass 2026-09-13; `9d8588c` | No CloudEvents builder; consumer supplies envelope |
| `docs/plans/django-upgrade-plan.md` | Phase 11 Celery gate | done; gate passed | E3; Django guide | `make_app`, retry kwargs implemented | plan second pass 2026-09-13; `9d8588c` | None |
| `docs/plans/django-upgrade-plan.md` | Phase 12 schema and casing | done, later revised | E3; E4 R1/R4/R7 | drf-spectacular retained; custom casing; RawPassthroughField built; mirrors later removed by R4 | plan status 2026-09-12; R4 2026-09-23 | Original DRF mirror claim obsolete after R4 |
| `docs/plans/django-upgrade-plan.md` | Phase 13 conformance driver | done | E3 | Driver runs shared cases | plan status 2026-09-12; `9d8588c` | Historical pass is not a fresh run |
| `docs/plans/django-upgrade-plan.md` | Deferred claim-check | deferred | E13 | Commons-shaped; second storage backend trigger | plan Deferred; review E13 | Duplicate of commons plan deferred item; one current owner |
| `docs/plans/django-upgrade-plan.md` | Deferred cloud messaging adapters | deferred | E13 | Second cloud backend trigger | plan Deferred | Missing from review register/closed list |
| `docs/plans/django-upgrade-plan.md` | Deferred `RawPassthroughField` | done | E3 | Built in Phase 12 | plan status 2026-09-12 | Deferred list not updated; later status wins |
| `docs/plans/django-upgrade-plan.md` | Deferred `AUTH.OIDC` settings block | deferred | E13 | Await second consumer | plan Deferred | Missing from review register/closed list |
| `docs/plans/django-upgrade-plan.md` | Not in this plan: lower Python floor | historical-only | context | Dropped as prerequisite; revisit only on consumer need | plan Not in this plan | Missing from review register/closed list; not active work |
| `docs/plans/django-upgrade-plan.md` | Not in this plan: transfer overlap | done | E4 R7 | Views replaced by library-backed implementation | plan Not in this plan; R7 2026-09-23 | Plan says planned; later R7 says done |
| `docs/plans/django-upgrade-plan.md` | Not in this plan: `RequestUtils` name collision | deferred | E13 | Breaking fix needs separate plan | plan Not in this plan | Missing from review register/closed list |
| `docs/plans/django-upgrade-plan.md` | Not in this plan: cims adoption | downstream | E12 or historical context | Consumer-owned; no pykit implementation | plan Not in this plan | None |
| `docs/plans/azure-library-plan.md` | Alignment §§1–7 (D46, D55) | historical design | E7; ADR-0001/0002/0006 | Package plan parked; no Azure package exists | plan header 2026-09-13 | Proposed release alignment must not assign a release |
| `docs/plans/azure-library-plan.md` | Summary, conventions, exclusions, testing | historical design | E7; context | Deferred design evidence only | plan header 2026-09-13 | `rn_forge.web.context` example obsolete after R3; no package implementation |
| `docs/plans/azure-library-plan.md` | Things deliberately not in package: protocol definitions | excluded ownership | E1; E7 | Commons owns protocols; Azure would implement them | plan exclusions | None |
| `docs/plans/azure-library-plan.md` | Things deliberately not in package: infrastructure provisioning | rejected scope | context | No ARM/Bicep/Terraform or resource creation | plan exclusions | None |
| `docs/plans/azure-library-plan.md` | Things deliberately not in package: Azure Cache for Redis adapter | rejected scope | context | Generic redis-py connection suffices; any port is commons/standalone concern | plan exclusions | Missing from review register/closed list |
| `docs/plans/azure-library-plan.md` | Phase 0 scaffold and gates | deferred | E7 | Package scaffold waits for owner scheduling; protocol prerequisites alone do not start Azure work | Plan parked 2026-09-13 | Namespace choice open |
| `docs/plans/azure-library-plan.md` | Phase 0.1 protocol prerequisites | done prerequisite | E7; E1 | Commons SecretStore/ObjectStore/MessageBus prerequisites landed | plan 2026-09-10 | Do not mark Azure Phase 0 built |
| `docs/plans/azure-library-plan.md` | Phase 0.2 scaffold and namespace | deferred | E7 | Owner scheduling and namespace decision pending | plan parked 2026-09-13 | Namespace undecided; no scaffold |
| `docs/plans/azure-library-plan.md` | Phase 1 credentials | deferred | E7 | Credential chain unbuilt | plan parked 2026-09-13 | None |
| `docs/plans/azure-library-plan.md` | Phase 1.1 error translation | deferred | E7 | Design only | plan parked 2026-09-13 | None |
| `docs/plans/azure-library-plan.md` | Phase 2 Key Vault | deferred | E7 | SecretStore adapter unbuilt | plan parked 2026-09-13 | None |
| `docs/plans/azure-library-plan.md` | Phase 3 Blob | deferred | E7 | ObjectStore adapter unbuilt | plan parked 2026-09-13 | None |
| `docs/plans/azure-library-plan.md` | Phase 4/4.1 Service Bus gate | gated deferred | E7 | Requires protocol, real adopter, test strategy | plan parked 2026-09-13 | Gate outcome open |
| `docs/plans/azure-library-plan.md` | Phase 4.2 Service Bus adapter | gated deferred | E7 | Build only if Phase 4.1 passes | plan parked 2026-09-13 | Gate outcome open |
| `docs/plans/azure-library-plan.md` | Phase 5/5.1 Azure Monitor gate | gated deferred | E7 | Requires consumer and useful replacement scope | plan parked 2026-09-13 | Gate outcome open |
| `docs/plans/azure-library-plan.md` | Phase 5.2 Azure Monitor adapter | gated deferred | E7 | Build only if Phase 5.1 passes | plan parked 2026-09-13 | Gate outcome open |
| `docs/plans/azure-library-plan.md` | Deferred Azure OpenAI | deferred | E7 | Second LLM supplier would trigger separate LLM package | plan Deferred | Register E7 groups item; preserve distinct trigger |
| `docs/plans/azure-library-plan.md` | Deferred Azure DevOps | deferred | E7 | Generic machinery belongs commons; no Azure adapter now | plan Deferred | Register E7 groups item |
| `docs/plans/azure-library-plan.md` | Deferred managed-identity PostgreSQL | deferred | E7 | Trigger: deployment forbids passwords | plan Deferred | Register E7 groups item |
| `docs/plans/azure-library-plan.md` | Deferred Entra ID auth classes | rejected as code | E7; context | Generic OIDC plus recipe covers need | plan Deferred | Register says adapter deferred; source says “Not code” |
| `docs/plans/azure-library-plan.md` | Deferred blob-lease `LockPort` | deferred | E7 | Multi-host trigger; port redesign first | plan Deferred | Missing from review register/closed list |
| `docs/plans/azure-library-plan.md` | Not in this plan: cims/intellibench adoption | downstream | E12 or context | Consumer repos own adoption | plan Not in this plan | None |
| `docs/plans/standards-rebaseline-plan.md` | Premise, review findings, order of authority | accepted decision | ADR-0003; E4 | Standards/framework first; rationale retained | plan 2026-09-21 to 23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R1 OpenAPI accuracy | done | E4 | Implemented; withdrew reuse Phase 1 and Page naming | commit `373d6bc`; review What is done | None |
| `docs/plans/standards-rebaseline-plan.md` | R2 standards deviations | done | E4 | Implemented | commit `373d6bc`; review What is done | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 Part A | done, partly superseded | E4 | Shared web logic landed; correlation-ID parts superseded by R3 | commit `373d6bc`; R3 2026-09-23 | Preserve supersession |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B1 health | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B2 discovery | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B3 deprecation/sunset | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B4 conditional GET | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B5 Retry-After | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B6 security headers | done | E4 | Implemented service surface | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B7 body limit | done | E4 | Kit middleware retained after R10.3 probe | commit `373d6bc`; R10.3 status 2026-09-23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B8 CORS | done | E4 | Supersedes reuse Phase 6 | commit `373d6bc`; review Closed items | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B9 access log | superseded | E4 | Implemented then deleted by R10.2 | commit `373d6bc`; R10.2 2026-09-23 | Old service-surface text describes removed behavior |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B10 idempotency runner | done | E4 | Implemented | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B11 VersionConflict | done | E4 | Implemented | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R2.5 B12 deployment guide | done | E4; package guides | Implemented guide | commit `373d6bc` | None |
| `docs/plans/standards-rebaseline-plan.md` | R3 Trace Context | done | E4 | Implemented and committed; replaced correlation header/middleware | commit `630142c`; review Second review | Plan Order says uncommitted; stale |
| `docs/plans/standards-rebaseline-plan.md` | R4 one model per stack | done | E4 | Implemented and committed; removed pydantic mirrors | commit `df7a245`; review Second review | None |
| `docs/plans/standards-rebaseline-plan.md` | R5 library evaluations | closed evaluation | E4; context | Five candidates exempt; no dependencies added | probes 2026-09-23; commits `74b36ff`, `c1979a4` per review | R5 header says four with fifth added later; preserve fifth |
| `docs/plans/standards-rebaseline-plan.md` | R6 Django scope | release gate/deferred | E8 F8.1/F8.2 | Split decision before release; auth review deferred; transfer settled by R7 | plan 2026-09-23; board/review Q4 | R6 says nothing scheduled; board makes split release gate |
| `docs/plans/standards-rebaseline-plan.md` | R7 transfer/bulk | done | E4 | tablib + django-import-export adopted, FastAPI transfer added | commits `cc78e19`, `a036a50` per review | Earlier plan says ready to implement |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP adoption | done with deferred tails | E4; E13 | Sorting, fields, timestamp, operation and conventions implemented | commit `9af1705` per review; status 2026-09-23 | Review asks verify commit; source final leftovers falsely lists built Operation dataclass |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-231/234 batch handlers | deferred | E13 | Adopted spelling; handlers on demand | R8 status 2026-09-23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-164 soft delete | deferred | E13 | Owner skipped; revisit for consumer | R8 owner 2026-09-23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R8 multi-term orderBy | deferred | E13 | Ideate composite keyset before build | R8 status 2026-09-23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-157 `readMask` | deferred | E13 | Payload-size problem trigger | R8 AIP table | Missing from review register/closed list |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-193/154/155/160/122 | rejected | E4; context | RFC problem, ETag header, Idempotency-Key header and native filtering/IDs govern | R8 AIP table | Not enumerated in review closed list |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-134 `updateMask` | rejected alternative | E4; context | RFC 7396 merge patch; convention wording adopted | R8 AIP table | Not enumerated in review closed list |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-180 oasdiff handoff | kiln-owned | E12 | Golden repo CI note | R8 status 2026-09-23; review E12 | None |
| `docs/plans/standards-rebaseline-plan.md` | R8 AIP-136 gateway check | kiln-owned | E12 | Golden repo acceptance | R8 status 2026-09-23; review E12 | None |
| `docs/plans/standards-rebaseline-plan.md` | R9 SQLAlchemy and tablib | done with deferred tail | E4; E13 | SQLAlchemy package created; rest waits for consumer | commit `653ac47`; review Second review | Source R9 status and Order say uncommitted; stale |
| `docs/plans/standards-rebaseline-plan.md` | R9 fastapi-import-export, sqlakeyset evaluations | closed evaluation | E4; context | Both exempt; no adoption task | R9 decisions/status 2026-09-23 | None |
| `docs/plans/standards-rebaseline-plan.md` | R9 SQL idempotency/session/readiness | deferred | E13 | Build when SQLAlchemy application asks | R9 Q1 2026-09-23; review E13 | None |
| `docs/plans/standards-rebaseline-plan.md` | R10.1 docs repair | done | E4 | R3 docs repaired | R10 status 2026-09-23; review commit `74b36ff` | None |
| `docs/plans/standards-rebaseline-plan.md` | R10.2 access log removal | done | E4 | Access log and Django middleware removed | R10 status 2026-09-23; review commit `74b36ff` | Supersedes Django Phase 7 and B9 |
| `docs/plans/standards-rebaseline-plan.md` | R10.3 Starlette body limit | rejected at probe | E4; context closed item | Kit middleware retained; `asgi.py` removal withdrawn | R10 probe 2026-09-23; review Closed items | None |
| `docs/plans/standards-rebaseline-plan.md` | R10.4 OTel processor | done | E4 | Moved to commons | R10 status 2026-09-23; review commit `74b36ff` | None |
| `docs/plans/standards-rebaseline-plan.md` | R10.5 `traceId` | done | E4 | Problem extension renamed; log `trace_id` remains | R10 status 2026-09-23; review commit `74b36ff` | None |
| `docs/plans/standards-rebaseline-plan.md` | Effect on other plans / Order | historical reconciliation | context | Supersessions recorded above | plan 2026-09-23 | Order calls committed R3/R9 uncommitted and schedules done work |
| `docs/plans/standards-rebaseline-plan.md` | Validation | historical evidence | context | Date-stamped results only; no fresh claim | plan 2026-09-23 | None |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.1 | planned | `E9/F9.1` | Add SQLAlchemy CI coverage in a separate implementation task. | Review F2; workflow inspection 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.2 | planned | `E9/F9.2` | Make CI docs build strict in a separate implementation task. | Review F4; workflow inspection 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.3 | planned / owner choice | `E9/F9.3`; release runbook | Document automatic tagging on main push; decide enforcement of dependency order. | Review F2, 2026-09-23. | CI ordering decision open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.4; Q5 | owner decision | `E9/F9.4`; proposed `release-1` | Confirm whether all seven workspace packages join first coordinated batch. | Seven manifests, 2026-09-23. | Q5 open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.5 | planned | `E9/F9.5` | Verify remote tags and external installation without workspace override after tag cut. | Review F2; 2026-09-23 local refs only. | No remote evidence yet. |
| `docs/plans/reviews/docs-structure-review.md` | Open register F9.6 | owner release action | `E9/F9.6`; release runbook | Coordinated tag cut awaits explicit owner authorization and kiln E7 trigger. | Review F2; no new local tags 2026-09-23. | Release approval and Q4/Q5 open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register F10.1 / Batch 1 | done documentation work | `E10/F10.1` | Baseline and 309-row ledger completed in this working tree. | Review instructions; ledger, 2026-09-24. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F10.2 / Batch 2 | done documentation work | `E10/F10.2` | Routing, architecture, guides, ADRs and work records completed in this working tree. | Review instructions; current docs, 2026-09-24. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F10.3 / Batch 3 | done documentation work | `E10/F10.3` | Board, proposed release page and history archive completed in this working tree. | Review instructions; current docs, 2026-09-24. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F10.4 / Batch 4 | done documentation work | `E10/F10.4` | Root nav, archive exclusion and package consumer pages completed in this working tree. | Review instructions; current docs, 2026-09-24. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F10.5 / Batch 5 | done documentation work | `E10/F10.5` | Root and seven package sites built strictly; status, mapping, link and scope checks passed. | Validation record, 2026-09-24. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register F8.1; Q4 | release gate / owner decision | `E8/F8.1` | Decide Django package split before tags; do not choose split outcome here. | Board backlog; review Q4, 2026-09-23. | Q4 open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register F8.2 | deferred | `E8/F8.2` | Review auth as one piece when owner schedules it; carry SAML-to-JWT note verbatim. | Board backlog; Q7 default, 2026-09-23. | Auth scope open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register Q9 | open release assignment | `E6/F6.1`; `E6/F6.2` | Features remain planned without release assignment until owner decides. | Review Q9, 2026-09-23. | Q9 open. |
| `docs/plans/reviews/docs-structure-review.md` | Open register E11 | kiln-owned deferred | `E11` | Codegen fences exist; generator work awaits kiln D2/D37. | Board; review register, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register E13: `:batchGet`, `:batchUpdate`; AIP-164; multi-column sorting | deferred | `E13` | Build only under stated consumer or ideation triggers. | Board backlog; review register, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register E13: multi-tenant scope; SQLAlchemy helpers | deferred | `E13` | Await second tenant model or SQLAlchemy application need. | Web deferred list; R9, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Open register E6 acceptance note | consumer-owned deferred | `E6` | Account Portal and IntelliBuild acceptance waits for those apps to unpark. | Reuse plan; review register, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Kiln handoff: `golden/python-app`; `golden/python-tool`; `golden/python-web-api`; `golden/python-web-app-django` | kiln-owned deferred | `E12` | Kiln owns runnable golden-repo acceptance. | Review E12 table, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Kiln handoff: F4.2; F.1; `oasdiff`; AIP-136 gateways | kiln-owned deferred | `E12` | Config-manager adoption, package re-seed, golden CI note and gateway check remain kiln work. | Review E12 table, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Kiln handoff: E7 SQLAlchemy tag order; old ADR and namespace references | kiln correction / open owner decision | `E12` | Record downstream corrections; do not edit kiln. | Review second pass/F7, 2026-09-23. | Q10 open, conditional on Q5. |
| `docs/plans/reviews/docs-structure-review.md` | Closed: `X-Correlation-ID`; access log; `Page<Item>` names; pydantic mirrors | closed / removed | `E4` considered and rejected | Keep historical provenance only. | R1/R3/R4/R10, 2026-09-23. | — |
| `docs/plans/reviews/docs-structure-review.md` | Closed: forward-only cursor, no `previousPageToken` | closed / rejected | `E2`; `E3` considered and rejected | No reverse cursor contract. | Owner gate, 2026-09-12. | — |

**Ledger rows:** 309.

## Plan items absent from the review register and closed list

The review aggregates major work. These smaller explicit plan items need their own disposition; the ledger above gives the source and destination. Related exclusions remain historical unless a separate decision opens them.

| Source | Additional item | Disposition |
| --- | --- | --- |
| Commons | Phase 5.1 `mergedeep`; 5.3 atomic-write proposal; 11.4 old YAML extra; 18.3 `Environment.rnf_home`; E.1 `StrictDataclassMixin` | Rejected, replaced or withdrawn; E1/context. |
| Lifecycle retirement | Kiln template/config migration substeps | Kiln-owned historical handoff; E5/E12. |
| Web and FastAPI plans | LLM/Azure port; consumer rewrites; lower Python floor; WebSockets/background tasks; extra app-layer utility endpoints | Deferred or explicit scope exclusions; E7, E12 or history as mapped. |
| Consumer reuse | Finding 11 config guidance; Phase 0 fluent builder; early hand-written SSE encoder | Guidance belongs to package docs; two alternatives rejected, E3/E6 history. |
| Django plan | Cloud messaging adapters; `AUTH.OIDC` settings block; `RequestUtils` collision | Deferred with their original triggers; E13. |
| Azure plan | Blob-lease `LockPort`; Redis adapter exclusion | Deferred E7; explicit scope exclusion in history, respectively. |
| Standards R8 | AIP-157 `readMask`; AIP-193/154/155/134/160/122 alternatives | Deferred E13; rejected alternatives E4/history. |
| Standards R9/R5 | `sqlakeyset` and `fastapi-import-export` evaluations | Exempt after probes; E4/history. The review closed list names only the earlier four R5 libraries. |
| Board | Conformance flake fix and its seed/25-run evidence | Done historical validation; E4/context. |
| Original CIMS survey | Tier 1.5/1.6 mixins and Tier 3.5 nested-dict escape hatch | Mixins were delivered in Django Phase 5; `RawPassthroughField` was delivered later. The old survey is not new open work. |

## Conflicts retained for reconciliation

| ID | Source conflict | Current evidence / later disposition |
| --- | --- | --- |
| C1 | The plan board and several plan status paragraphs call R3, R4, R9, R10 and commons G uncommitted or in the working tree. | Commits `630142c`, `df7a245`, `653ac47`, `74b36ff` and `231a68e` exist. Keep original dated claims as history. |
| C2 | The board calls reuse Phase 5 active and Phase 6 planned. | R3 withdrew Phase 5; R2.5 B8 delivered CORS. |
| C3 | Commons F and the kiln handoff still describe `[cli.lifecycle]` as current. | Lifecycle retirement `1a8241b` moved composition to tooling-owned `[lifecycle]`. |
| C4 | Board, commons D.8 and kiln tag order omit `rn-forge-sqlalchemy`. | The package exists, but first-batch scope Q5 and kiln correction Q10 remain open. |
| C5 | R8 final “leftovers” sentence calls the AIP-151 `Operation` model pending. | `rn_forge.web.Operation`, tests and commit `9af1705` exist; only later consumers remain on demand. |
| C6 | R6 says no Django scope work is scheduled. | The later board makes the split decision a pre-tag gate; Q4 leaves the outcome open. |
| C7 | Older Django, web and FastAPI plans describe correlation middleware, access logging, DRF serializers, FastAPI pydantic mirrors and `Page<Item>` naming. | R1/R3/R4/R10 removed or replaced them. Preserve old sections as history, not current contracts. |
| C8 | Azure plan says Entra auth classes are a recipe rather than code; the review register groups them with deferred adapters. | Preserve source distinction in E7; no adapter is authorized by this documentation batch. |
| C9 | Original CIMS survey recommends no structlog support and different package destinations for HTTP features. | Commons Phase 9 built `StructLogger`; web and framework plans own the current HTTP contract. |
| C10 | Review F2 describes a manual dependency-order tag cut while `_package-ci.yml` automatically tags on main push. | E9/F9.3 must document actual mechanics; enforcement remains an owner choice. |
| C11 | Q9 proposes assigning redaction and SSE to the first release; Q5 proposes seven-package batch scope. | Both assignments remain open. The features stay `planned` without a release assignment. |

## Archive normalization record, 2026-09-24

The SHA-256 values above were checked against the original files immediately before their filesystem moves. Each matched. The original bytes also remain in Git history at the baseline HEAD. The archive copies contain only a historical banner and relative link/path corrections; these are the permitted normalizations. They are frozen after this pass.

| Original source | Archive path | Normalization |
| --- | --- | --- |
| `docs/01-extraction-from-cims.md` | `docs/plans/archive/01-extraction-from-cims.md` | Historical banner; old `README.md` plan link points to `plan-board.md`. Other sibling plan links become valid at this location. |
| `docs/plans/README.md` | `docs/plans/archive/plan-board.md` | Historical banner; 15 relative links corrected for the new location, including two links to the stable kiln handoff. |
| `docs/plans/azure-library-plan.md` | `docs/plans/archive/azure-library-plan.md` | Historical banner; 3 relative links corrected. |
| `docs/plans/cli-lifecycle-namespace-plan.md` | `docs/plans/archive/cli-lifecycle-namespace-plan.md` | Historical banner; full superseded design retained. A short pointer occupies the old path for kiln. |
| `docs/plans/cli-lifecycle-retirement-plan.md` | `docs/plans/archive/cli-lifecycle-retirement-plan.md` | Historical banner; no link correction required. |
| `docs/plans/commons-upgrade-plan.md` | `docs/plans/archive/commons-upgrade-plan.md` | Historical banner; 6 relative links corrected. |
| `docs/plans/django-upgrade-plan.md` | `docs/plans/archive/django-upgrade-plan.md` | Historical banner; 14 relative links corrected. |
| `docs/plans/fastapi-app-layer-plan.md` | `docs/plans/archive/fastapi-app-layer-plan.md` | Historical banner; 2 relative links corrected. |
| `docs/plans/fastapi-library-plan.md` | `docs/plans/archive/fastapi-library-plan.md` | Historical banner; 4 relative links corrected. |
| `docs/plans/standards-rebaseline-plan.md` | `docs/plans/archive/standards-rebaseline-plan.md` | Historical banner; 2 relative links corrected. |
| `docs/plans/web-api-reuse-plan.md` | `docs/plans/archive/web-api-reuse-plan.md` | Historical banner; no link correction required. |
| `docs/plans/web-library-plan.md` | `docs/plans/archive/web-library-plan.md` | Historical banner; 6 relative links corrected. |

`docs/plans/index.md` now routes readers to the current spec board and this ledger. The stable `docs/plans/kiln-dependencies.md` and this review remain in place. Raw archives are repository evidence; current pages do not link into them.

The review's three relative links to moved plans were changed to source-path text. This keeps its evidence locatable without publishing links into excluded archives. Its kiln handoff link remains live.

## Package-page history moved in Batch 4

| Original source | Historical claim | Current home |
| --- | --- | --- |
| `packages/rn-forge-django/README.md`, “Dependencies and why”; `docs/guides/openapi.md`, “Why there is no camelCase dependency” | The package evaluated `djangorestframework-camel-case` and chose its own renderer, parser and schema hook. The old text gave the candidate's 2023 release and Python classifiers as reasons. | The package README and OpenAPI guide state the current `drf.casing` contract. This evaluation stays historical. |
| `packages/rn-forge-django/README.md`, “Dependencies and why” | Celery 5.6.3 was checked against Python 3.14 on 2026-09-12 despite then-stale classifiers. | The package README states the current `celery` extra; validation remains dated evidence here. |
