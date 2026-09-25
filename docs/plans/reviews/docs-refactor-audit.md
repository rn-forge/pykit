# Documentation refactor audit

**Date:** 2026-09-25 · **Status:** open for discussion; no recommendation below has been applied.
**Compares:** `12da7f3` (before the refactor) with `472bfa4` (the refactor), on `feature/upgrade`.
**Also read:** `rn-forge/kiln` at `feature/v1` (`a4a3541`), for its documentation rules and for what
it expects from pykit.

This audit checks the refactor against the seven questions the owner asked. Each question gets a
verdict, then numbered findings. Every finding gives the evidence and a proposed fix. Nothing has
been fixed yet: we review this page first, then implement.

## Verdicts

| # | Question | Verdict |
| --- | --- | --- |
| 1 | Nothing from the original documents is missing | **Not certified.** The twelve archived files are faithful copies. The pages that were rewritten in place lost content, and one handoff kiln depends on lost its design sections. See [L1–L10](#1-is-anything-missing). |
| 2 | ADRs are real decisions, not history or requirements | **Mostly certified.** All seven are decisions. One bundles two decisions, one rests on an owner approval nobody can confirm, and several durable decisions have no ADR. See [D1–D7](#2-are-the-adrs-real-decisions). |
| 3 | Epics, features and stories follow one standard | **Not certified.** A second status axis ("Readiness") was invented, done epics have no feature IDs, stories repeat their feature's acceptance, and vocabulary drifts. See [S1–S10](#3-do-epics-features-and-stories-follow-one-standard). |
| 4 | Release pages show the correct implementation status | **Partly certified.** The facts are right: tags, versions and manifest edges all check out. The runbook's order of steps cannot work, and the release page was cut before it had scope. See [R1–R7](#4-do-the-release-pages-show-the-correct-status). |
| 5 | Everything in progress is parked in the backlog | **Mostly certified.** Every row of the review's open-work register has a home. A live kiln blocker never reached pykit, and a release gate sits inside a deferred epic. See [B1–B5](#5-is-all-open-work-parked-in-the-backlog). |
| 6 | The content reads naturally | **Not certified.** The architecture pages read well. The spec, release and index pages read like generated compliance text. See [W1–W6](#6-does-it-read-naturally). |
| 7 | Other issues | See [O1–O10](#7-other-issues). |

What works well, so it is not lost in the fixes:

- The ten plans, the old board and the CIMS survey were archived byte-for-byte, apart from a
  one-line banner and relative-link repairs. I diffed each against `12da7f3`.
- The ledger in `plans/context.md` is thorough: 309 rows, every old phase, R-item and D-number
  searchable, and eleven recorded conflicts.
- The root site and all seven package sites build with `--strict`, with no warnings or anchor
  diagnostics (see [Verification record](#verification-record)).
- `architecture/workspace.md` and `architecture/authentication.md` match the manifests and
  `.importlinter`, and they read well.

## 1. Is anything missing?

The archive copies are complete, so the risk is in the pages that were **rewritten in place with no
archive copy**: `plans/kiln-dependencies.md`, `auth-overview.md`, `index.md`, and the web adoption
pages. Content was also lost where a long plan section became a short feature file.

### L1 — The kiln handoff lost the sections kiln cites it for (High)

The old `plans/kiln-dependencies.md` (349 lines) was rewritten into a 57-line pointer page. Unlike
every other plan, the original was not copied into `plans/archive/`; the page says it survives
only in Git history.

Kiln still sends readers to this path for content that is no longer there. Kiln's
`docs/plans/context.md` maps:

- §2.9, the tool-lifecycle mechanism → "mechanism in the pykit handoff";
- §2.11 and D55, the three libraries' package layout → "pykit handoff";
- its §4 risk list → "pykit handoff (C.3 growth)", the installer-framework risk and its guard.

The rewrite dropped all three: §3.2's layout tree and the rule "modules are grouped; public class
names do not move"; §2.1's `ToolProduct` design and its four recorded deviations; and the "Risk,
and its guard" paragraph. §3.1's ownership line ("Kiln-owned: `$RNF_HOME`, the `.rn-forge/`
layout, `config.toml` schemas, archetypes, golden repos and product policy") is gone too.

**Fix:** copy the `12da7f3` text to `plans/archive/kiln-dependencies.md`, like the other plans.
Then either keep §2.1 and §3 verbatim at the stable path, under a "Design kiln relies on"
heading, or link each current-destination row to the archived section. Kiln cites the path, not
its headings, so either works.

### L2 — Model conventions were weakened from normative to advisory (High, needs owner decision)

`packages/rn-forge-web/docs/adoption/model-conventions.md` was labelled "Normative for the ORM
packages". The rewrite replaced 116 lines with a comparison table and "optional advice". Removed:

- audit-column semantics: nullability, `create_time == update_time` on insert, and the actor
  being `Principal.subject`;
- the shared `status` vocabulary (`ACTIVE` / `INACTIVE` / `DELETED`) and the rule that domain
  lifecycles get their own column;
- the natural-key rules: ordered field list, dotted paths, unique together, non-null, stable;
- the soft-delete rules: deletion as a status transition, excluded by default, reversible by a
  versioned write, hard delete as a separate operation, and 404 on deleting an already-deleted
  resource;
- the explanation of why there is no shared base class. ADR-0004 now carries a shorter version.

The review's Q6 recommended "document only implemented guarantees", so the direction was expected.
But it removes a normative contract the owner wrote. No ledger row records the removed rules, and
the old soft-delete rule now conflicts with E13's deferred AIP-164 soft delete, with nothing noting
it.

**Fix:** confirm Q6 (see [O2](#o2-owner-answers-are-recorded-but-cannot-be-traced)). If
confirmed, record each removed rule in the ledger and open a deferred E13 row for "shared model
vocabulary for SQLAlchemy", so the old contract has a home. If not, restore the page and list
where each package falls short.

### L3 — The design for the two planned features was dropped (High)

`web-api-reuse-plan.md` Phase 2 and Phase 3 were implementation-ready. F6.1 and F6.2 now hold a
paragraph each.

- **F6.1 lost:** `RedactionPolicy` and its default patterns, `RedactFilter` and where it
  registers, `LoggingConfig.redact`, the structlog processor, the non-mutation and `None`/`""`
  rules, the named exemption, and the nine test cases.
- **F6.2 lost:** the `sse_response` signature; newline validation instead of silent mangling;
  the terminal problem frame; the `sse` extra and dev-group wiring; the uvicorn
  `AppStatus` monkey-patch as the reason it is an extra; the rule "no SSE cases in `CASES`"; and
  the tests.

Both features are then marked "not ready" and ask questions the source already answers. F6.2's
open question asks "which named consumer will verify it?" while its own header names PhotoTidy and
Apollo. Kiln's rule is that design for unbuilt work lives in the feature's `## Design`. The archive
is excluded from the site, so readers cannot reach it.

**Fix:** move each phase's Build, Rules and Tests into `## Design`. Keep only the real open
questions:

- F6.1: Account Portal, its acceptance consumer, was parked on 2026-09-21. Who accepts it now?
- F6.2: the design reads `get_correlation_id()` and `DEFAULT_CORRELATION_HEADER`, which R3
  removed. Replace them with the trace context.

### L4 — Standing rules that did not reach an ADR or a guide (Medium)

The old board's "Standing rules for every plan" carried rules that now appear nowhere current:

- **Adopted first** (2026-09-23): once a library or framework is adopted for a concern, delete
  everything in the kit it already does, including code that predates it.
- **Wire indistinguishability:** a consumer must not be able to tell from the wire whether an API
  was built with pykit, with native libraries, or on another stack.
- **AIPs rank below RFCs:** they break ties and are not a design commitment (R8 premise).
- **cims and intellibench are prior art, not compatibility constraints.** The phrase survives
  only in the root README's history.
- **Do not create `rn-forge-selfkit`:** shared installer mechanics stay in tooling (Phase 18.4
  resolution).

**Fix:** add the first three to ADR-0003 (see [D3](#d3-adr-0003-states-the-principle-but-not-its-operative-rules-medium)).
Put the fourth in `guides/choosing-packages.md` or ADR-0003's Background. Record the fifth on
E13's `ProductInstaller` row.

### L5 — The auth overview lost its standards and scope lines (Medium)

The old page ended up in `architecture/authentication.md` and the package guides. Most setup steps
survive in the Django auth and FastAPI wiring guides; I checked. Lost:

- the standards each layer implements: RFC 7519, 7517 and 8414 and OIDC Discovery for commons;
  RFC 6750 §3, 7617 and 9457 for web;
- the per-stack mechanism matrix, including Basic auth as "dev/internal only". The new page does
  not mention Basic at all;
- "pykit is not an authorization server; OAuth2 authorization code / PKCE is deliberately out of
  scope". This is a durable scope decision.

**Fix:** add the standards column and the mechanism matrix back to
`architecture/authentication.md`. Record the authorization-server exclusion as an ADR, or as a
constraint on F8.2.

### L6 — A normative line in the API conventions was changed to pass a grep (Medium)

The review's checklist banned `X-Correlation-ID` from current pages. `api-conventions.md` said
"**`X-Correlation-ID` is not read and not sent**", a precise, current, tested statement
(`tracing.house-header-is-not-echoed`). It now says "Proprietary request identifiers are ignored
and never echoed". That is vaguer, and broader than the conformance case checks.

**Fix:** restore the original sentence. The grep rule was meant for stale descriptions of removed
behavior, not for statements that the behavior is gone.

### L7 — `StrictDataclassMixin` is recorded as removed, but it exists (Medium)

The ledger (rows for the board's close-out, commons E.1 and the "absent items" table) and E1's
"Considered and rejected" say `StrictDataclassMixin` was removed by E.1a. The class exists in
`rn_forge/commons/lang/dataclasses.py` and is exported from the facade. It was re-added in
`231a68e` with a new meaning: reject unknown keys. The commons data guide and README describe it
correctly.

The plan said "gone", the code says otherwise, and the ledger followed the plan. The review's own
removed-symbol list has the same error. Codex did not remove the package docs, which was the right
call.

**Fix:** correct the three ledger rows and E1. Add a conflict row: "E.1a removed the class;
`231a68e` reintroduced the name for unknown-key rejection".

### L8 — `CLAUDE.md` lost an agent guardrail (Low)

The old start section said `rn-forge-azure` is parked and "do not start … without being asked".
The new section routes to the board and drops the instruction. E7 is `deferred`, but an agent
could read "deferred with entry criteria" as permission to elaborate it.

**Fix:** add one line to `CLAUDE.md`: do not start or elaborate a deferred epic unless asked.

### L9 — The FastAPI wiring pointer lost its migration table (Low)

`web/docs/adoption/wiring-fastapi.md` had a correct table mapping old hand-written code to
`rn-forge-fastapi` calls, plus a tracing paragraph. Both were removed. The review asked to "remove
or label" the table, but the table was current and useful to anyone reading an older application.

**Fix:** keep the table under a heading like "If your application predates rn-forge-fastapi".

### L10 — Smaller ledger inconsistencies (Low)

- The row for survey Tier 3.5 says the nested-dict escape hatch "remains an uncommitted survey
  idea". The "absent items" table says `RawPassthroughField` delivered it.
- The row for review Batches 1–5 says "Batches 4–5 remain planned". The F10.4/F10.5 rows and the
  page header say done.
- The row for FastAPI "Deferred: OIDC/JWKS Security" says "Shipped", which breaks the no-"shipped"
  rule.
- The Django-plan claim-check row duplicates the commons row. It is marked as a duplicate, which is
  fine.

## 2. Are the ADRs real decisions?

All seven state a choice that constrains future work. None is a feature description or a history
narrative, and none restates a requirement. Their Background sections cite sources properly.
Issues:

### D1 — ADR-0006 decides two things (Medium)

It covers (a) situational dependencies live behind extras and outside the facade, and (b) protocols
live in the lowest package that can hold them, with adapters beside their technology. They change
for different reasons. (b) also overlaps ADR-0001's "Adding a shared protocol starts in the lowest
package".

**Fix:** keep ADR-0006 on extras and the facade. Move protocol placement into ADR-0001's
Decision.

### D2 — ADR-0007 rests on an approval nobody can confirm (Medium)

The review said ADR-0007 should stay `proposed` "until the owner adopts it". It is `accepted`, and
its Background says "The owner accepted those defaults on 2026-09-24". The ledger says the owner
answered on 2026-09-23. See [O2](#o2-owner-answers-are-recorded-but-cannot-be-traced).

It is also a documentation-governance rule rather than an architectural decision. Kiln keeps these
rules in `_structure.md` files. It is fine as an ADR if the owner wants one, but most of its text
repeats `docs/_structure.md`.

**Fix:** set it to `proposed` until the owner confirms. Consider folding it into
`docs/_structure.md`.

### D3 — ADR-0003 states the principle but not its operative rules (Medium)

"Use published standards … use an adopted framework … add pykit code where it supplies a missing
contract" is right, but it leaves out the rules that make it decidable: adopted-first deletion,
wire indistinguishability, AIPs below RFCs, and "parity is enforced by the conformance table, not
by review". See [L4](#l4-standing-rules-that-did-not-reach-an-adr-or-a-guide-medium). It also
restates README principles 1–2 almost word for word, which breaks "one fact, one home".

**Fix:** add the four rules to its Decision. Link the README principles instead of restating them.

### D4 — ADR-0002 leaves out the interim branch rule (Medium)

The old handoff §2.3 said that until the owner declares pykit stable, kiln consumes pykit from
`feature/upgrade`; this "suspends the pinned-git-tags rule; it does not reverse it" (kiln D73).
Kiln's E7 still says so. ADR-0002 states only the tag rule. Today every pykit manifest pins an
uncut tag, so nothing resolves outside the workspace. That is the blocker in
[B1](#b1-kilns-live-blocker-on-resolvable-pins-is-not-recorded-high).

Its Consequences also say the runbook "describes current automation and dependency ordering". The
runbook says CI does not enforce ordering.

**Fix:** add the interim rule and its end condition to the Decision. Fix the Consequences
sentence.

### D5 — ADR dates and header format differ from kiln (Low)

Each ADR has `**Recorded:** 2026-09-24` but no original decision date. The review asked for both,
because the record date and the decision date are separate facts. Only ADR-0005 has one, as
`**Implemented:**`. Kiln puts status, date and scope on one line
(`**Status:** accepted (<date>) · **Scope:** …`).

**Fix:** add the original decision date, for example "decided 2026-09-12 (D52)", and use kiln's
one-line header.

### D6 — Durable decisions with no ADR (Medium)

These are cross-package choices that constrain future work. Today they live only in the ledger or
in package docs:

| Candidate | Source |
| --- | --- |
| W3C Trace Context replaces any house correlation header | R3, R10 |
| One wire model per stack, defined as pydantic models in `rn-forge-web` | R4 (ADR-0004 mentions it in Background only) |
| Cursor pagination is forward-only; no `previousPageToken` | Board gates, 2026-09-12 |
| pykit is not an authorization server; login flows are Django-only | Old `auth-overview.md` |
| Python floor stays `>=3.14` | Board standing rules |

Not all of these need an ADR. I would add the first and fourth. The forward-only cursor can live in
`api-conventions.md`. The Python floor needs a note only if someone asks to lower it.

### D7 — The board states more ADR-level rules than the ADRs (Low)

The old board's "Dependency direction" section explained why the development layer is two packages:
placement is decided by what an API's signature contains, not by who calls it today. ADR-0001 keeps
the result but not the rule, and the rule is what helps a maintainer place a new module.

**Fix:** add that sentence to ADR-0001.

## 3. Do epics, features and stories follow one standard?

The review adopted kiln's model: epic → feature `F<n>.<m>` → inline story `S<n>.<m>.<k>`, a
fixed status vocabulary, and one board group per epic. The refactor follows it only in part.

### S1 — A second status axis, "Readiness", was invented (High, needs owner decision)

Every unfinished epic, feature and release carries `**Readiness:** ready | not ready` and a
`**Readiness basis:**`. The word appears 112 times across 61 pages. It is not in kiln's rules or in
the review. Kiln handles the same idea with the `elaborating` status and a "To elaborate" board
group: work that is agreed but lacks stories or settled acceptance.

The extra axis makes every page carry two statuses, adds a paragraph of rules to
`specs/_structure.md` and `releases/_structure.md`, and produces combinations that are hard to
read. E6 is `planned` but not ready; E9 is `planned`, not ready, with two ready features; F8.1 is
"planned release gate".

**Fix:** unless the owner asked for this axis, drop it. Use `elaborating` for work whose
acceptance or design is unsettled (E6, F9.1, F9.3, F9.4, F9.6, F8.1). Use `planned` only once a
feature has stories and a release, as kiln does.

### S2 — Done epics have no feature IDs (Medium)

E1–E5 list "legacy feature" rows with no IDs and one pile of commit hashes per epic. So:

- release-1 cannot name its scope by ID. It says it "will link the selected implemented work from
  E1…E5";
- nobody can tell which commit delivered which row;
- kiln's shipped epics do give their features IDs, as rows.

**Fix:** number the rows (F1.1, F1.2, …) and give each its own `Implemented:` commits. The ledger
already has the mapping.

### S3 — Stories repeat their feature's acceptance (Medium)

Fourteen of the fifteen feature files have one story whose `**Acceptance:**` restates the feature's
`## Acceptance` list in other words (F6.1, F6.2, F8.1, F8.2, F9.1, F9.2, F9.4, F9.5, F9.6 and every
F10). Only F9.3 splits into real stories: "document" and "decide". Kiln's rule is that a decision
is its own story, and that the feature's acceptance block tags each line with the story it proves.

**Fix:** split where there is real work, for example F6.2 into dependency approval, module, docs
and consumer adoption. Tag each acceptance line with its story. Where a feature is one step, keep
one story and drop the duplicate feature-level list.

### S4 — Acceptance is prose, not checks (Low)

Kiln's acceptance blocks are runnable (`set -euo pipefail`, `absent`, `fails_with`). Pykit's are
bullet prose, even where a check is trivial. F9.1: `grep -q rn-forge-sqlalchemy
.github/workflows/main.yml`. F9.2: `grep -q 'mkdocs build --strict' .github/workflows/main.yml`.

**Fix:** add a short check block wherever a line can be scripted. Leave judgement lines as prose.

### S5 — E13 and E7 rows have no IDs (Medium)

E13 is a table of twelve proposals and E7 a table of eight items. None has an ID, so a release, a
question or a consumer request cannot point at one. Kiln's rule is that IDs are permanent and every
piece of work has one.

**Fix:** give each row a feature ID (F13.1…, F7.1…) while they are still rows. They become files
when promoted.

### S6 — Status vocabulary drifts (Low)

- "planned release gate" in E8's table is not a status.
- `**Status:** done` appears on 20 pages that are not work items: guides, runbooks, indexes,
  architecture pages, even `auth-overview.md`. A guide has no progress state.
- `releases/index.md` has a status and a readiness line, though it is an index.

**Fix:** status lines only on epics, features, stories and releases.

### S7 — Owner values drift (Low)

Owner values in use: "pykit", "pykit owner", "pykit release owner", "pykit release executor", "pykit
maintainers", "pykit documentation refactor", "kiln integration with pykit framework package
owners", and "pykit, when a named consumer supplies the need". There is one owner.

**Fix:** use two values, `pykit` and `kiln`. Say who acts in the text, where it matters.

### S8 — `Source:` lines cite paths that no longer exist (Low)

F8.1, F8.2, E8, E11 and F9.6 cite `docs/plans/README.md` and `docs/auth-overview.md` (old
content). Others cite a bare `web-api-reuse-plan.md`. The files now live under `plans/archive/`,
and `plan-board.md` replaced `README.md`.

**Fix:** one form everywhere: `plans/archive/<file>.md`, "<heading>".

### S9 — F9.5 and F9.6 depend on each other (Medium)

F9.5 (external installability) depends on F9.6 (tag cut), and F9.6's acceptance requires F9.5. The
runbook adds a third ordering: prove installs before merging. See [R2](#r2-the-release-runbooks-steps-cannot-be-followed-in-order-high).

**Fix:** F9.6 cuts the tags. F9.5 verifies after. The release's exit criteria require both.

### S10 — E10 still describes itself as uncommitted (Low)

The board row, F10.1 and the ledger say "completed in this working tree; no commit or release
claimed". The work is committed at `472bfa4`. F10.2's evidence line still quotes "the eight
baseline warnings", which F10.5 then says are gone.

**Fix:** set E10's `Implemented:` to `472bfa4` and drop the working-tree wording.

## 4. Do the release pages show the correct status?

**Facts checked and correct:** declared versions and internal edges in `release-1` match all seven
manifests, extras included. The remote has only `rn-forge-commons` and `rn-forge-django` tags up to
`v0.2.2` (`git ls-remote --tags origin`). No page claims a release. `main.yml` has no SQLAlchemy
job, and its docs job runs without `--strict`. `_package-ci.yml` creates missing tags and GitHub
Releases on a push to `main`. Every commit cited in E1–E5 exists and matches its subject.

### R1 — Release-1 was cut before it had scope (Medium)

Kiln's rule: "Cut a release page when there is scope to put on it, not ahead of time". The page has
no scope, a proposed matrix, and a gates table that repeats each feature's status and readiness.
Kiln: "a story's status belongs to the story". The page then needs a paragraph explaining why its
candidates do not block it.

**Fix:** until F9.4 is decided, keep the matrix on F9.4 as the proposal and delete release-1, or
reduce it to entry criteria plus "scope: not yet selected". Once scope exists, list story IDs only.

### R2 — The release runbook's steps cannot be followed in order (High)

Step 3 says: before merging to `main`, confirm each internal dependency's tag exists and installs
outside the workspace. But the tags are created **by** the merge. `_package-ci.yml` tags each
package after a push to `main`, and every job runs in parallel from the same commit. Before the
merge, the tags cannot exist.

Two further facts the runbook and F9.3 should state:

- **Order hardly matters in the current workflow.** All tags point at the same commit and are
  pushed within one run. The real risk is a partial run: one package's job fails, and its
  dependents are tagged with a pin to a tag that does not exist. F9.3 should frame the decision
  that way.
- **CI never proves external resolution.** Every job runs `uv sync --all-packages --all-extras
  --locked` with workspace sources. F9.5's check has to be a new job or a manual step after
  tagging.

**Fix:** rewrite the runbook as: before merge (decisions, scope, validation, approval) → merge →
watch every package job → verify remote tags and clean installs (F9.5) → record on the release
page. Move "partial publication" into F9.3's open question.

### R3 — The release trigger ignores kiln's live need (High)

The docs say releases wait for kiln E7's "owner declares pykit stable". Kiln's in-progress E5 is
blocked now on resolvable pins. See [B1](#b1-kilns-live-blocker-on-resolvable-pins-is-not-recorded-high).
The release area should record that trigger and its options: tag commons and web early, or pin the
web packages to `feature/upgrade` in the meantime.

### R4 — Done epics cannot be selected as release scope (Medium)

This follows from [S2](#s2-done-epics-have-no-feature-ids-medium). Release-1 would ship all of
E1–E5, but it can only point at whole epics.

### R5 — E2's commits are incomplete (Low)

Reuse Phase 4 (`unmapped_exceptions`) first appears in `373d6bc`, the R1/R2/R2.5 commit, not in
the two commits E2 lists. `FastApiApp` (reuse Phase 0) also first appears in `373d6bc`. E3 lists
that commit, so E3 is fine.

**Fix:** add `373d6bc` to E2, or better, to the row once rows have IDs.

### R6 — F9.1 is held back for a reason that does not apply (Low)

F9.1 is "not ready" because adding SQLAlchemy to CI "exposes publish behavior" pending F9.3. But
the SQLAlchemy job would behave exactly like the six existing jobs. Holding it back only leaves
SQLAlchemy untested in CI.

**Fix:** mark F9.1 ready. Record in F9.3 that the publish decision covers all seven jobs.

### R7 — The release area index reads like a status page (Low)

`releases/index.md` has `Status: planned` and `Readiness: not ready`, and three paragraphs on
release-1. Kiln's index is a newest-first list.

**Fix:** list release pages and link the runbook. Nothing else.

## 5. Is all open work parked in the backlog?

I checked every row of the review's open-work register and closed-items list, and every "missing
from register" row the ledger added:

- all active rows are in E6 and E9;
- all deferred rows are in E7, E8, E11 and E13;
- all kiln rows are in E12;
- every closed item appears only as *Considered and rejected* or in the ledger;
- no rejected item is marked as open work.

The extra items the ledger found (AIP-157 `readMask`, blob-lease `LockPort`, Django cloud
messaging, `AUTH.OIDC`, the `RequestUtils` collision) were placed correctly. Gaps:

### B1 — Kiln's live blocker on resolvable pins is not recorded (High)

Kiln's board ("Upstream work owned by pykit") and E5 say kiln's web cells cannot `uv sync` outside
pykit: `rn-forge-web`, `-django` and `-fastapi` pin `rn-forge-commons-v0.5.0` and
`rn-forge-web-v0.1.0`, and neither tag exists. Kiln lists two ways out: cut those tags, or pin to
`feature/upgrade`. Its F5.1 and S5.3.x depend on it. Pykit has no record of this: it is not in E9,
E12 or the handoff.

This was missing before the refactor as well, so it is not a codex loss. It is the most important
open cross-repo item, though.

Kiln's E5 also says `rn-forge-cli` and `rn-forge-tooling` already pin `feature/upgrade`. They do
not; both pin `rn-forge-commons-v0.5.0`. That is a kiln correction for E12.

**Fix:** add a feature to E9, "Make pykit resolvable for kiln before the stable release", with an
owner decision (early tags or branch pins) and acceptance "kiln's web cell `uv sync` succeeds".
Link it from the handoff and from E12.

### B2 — A release gate sits in a deferred epic (Medium)

F8.1, the Django split, must be decided before tags, but its epic E8 appears under **Deferred** on
the board. Someone scanning the board for release blockers will miss it.

**Fix:** move F8.1 into E9 as a decision story, for example S9.4.2. Or split E8 so the split
decision is a planned epic and the auth review stays deferred.

### B3 — E6 is "planned" with nothing scheduled (Low)

E6's features have no release, and F6.1's acceptance consumer is parked. In kiln's terms E6 is
`elaborating`, or `deferred` until Q9 is answered.

**Fix:** follow from Q9 and [S1](#s1-a-second-status-axis-readiness-was-invented-high-needs-owner-decision).

### B4 — Out-of-scope items have no current home (Low)

WebSockets and background tasks (FastAPI plan), extra app-layer utility endpoints (app-layer plan)
and a lower Python floor are "history only" in the ledger. That is correct: they are not work. A
reader of the current docs cannot tell they were considered.

**Fix:** add a short "Not planned" list to the owning epic's *Considered and rejected* (E3 for the
first two, `guides/development.md` for the floor).

### B5 — The kiln corrections list in E12 is incomplete (Low)

Add three rows:

- kiln's board still lists `[cli.lifecycle]` under C.3;
- kiln's E5 claims cli and tooling pin `feature/upgrade`;
- kiln's `context.md` cites the handoff for D55 and the lifecycle mechanism, which [L1](#l1-the-kiln-handoff-lost-the-sections-kiln-cites-it-for-high)
  restores.

## 6. Does it read naturally?

The architecture pages, the workspace table and the Django/FastAPI auth additions read like a person
wrote them. The spec, release, index and E10 pages do not. The patterns below account for most of
the "generated" feel.

### W1 — The same opening formula on every page

"It is for …" appears 17 times, nearly always as the second sentence of a page ("This page … It is for maintainers/implementers/the …").
Examples: "It is for implementers and the application that accepts the shared behavior" (F6.1);
"It is for the documentation maintainer handling Batch 5" (F10.5). The writing rules asked for an
opening line saying what the page covers and who it is for. Applied mechanically, it reads as a
template.

**Fix:** open with what the reader needs, and drop "It is for" unless the audience is surprising.
F6.1 could open: "Commons logging should strip secrets from structured events so applications stop
carrying their own redaction code."

### W2 — Defensive disclaimers

Recurring phrases: "no new tag implied" (5), "No release action is authorized", "not an
authorization to change auth behavior", "This documentation batch does not edit CI", "No release
assignment is implied", "It raises a design question; it does not change the current session or
token flow". There are 22 uses of "does not" across these pages. They answer a reviewer's checklist
rather than a reader's question. One statement on the board ("done means implemented, not tagged")
covers them all.

**Fix:** delete them from individual pages. Keep the single definition in `specs/_structure.md`
and on the board.

### W3 — Process talk on product pages

"Five batches completed in this working tree", "during the plan migration", "It prevents deferred
rows from becoming invisible during the plan migration" (E13), "the owner's Q1–Q3/Q6–Q8 defaults".
A reader six months from now has no use for the migration.

**Fix:** keep migration talk in E10 and `plans/context.md` only.

### W4 — Boilerplate headers on pages that do not need them

`**Status:** done` and `**Owner:** pykit.` sit on guides, runbooks, indexes and architecture pages
(24 owner lines, 32 status lines). See [S6](#s6-status-vocabulary-drifts-low).

### W5 — Abstract rule prose in the routing files

`releases/_structure.md` and `specs/_structure.md` are paragraphs of conditions, for example: "A
settled spec marked ready is not evidence that its implementation, validation or approval is
complete… not-ready candidate items are conditional blockers, not silently approved scope." Kiln's
equivalents are short tables and numbered steps.

**Fix:** once [S1](#s1-a-second-status-axis-readiness-was-invented-high-needs-owner-decision) is
settled, rewrite both in kiln's shape: "Belongs here / Does not belong here / Naming / Changing
this area".

### W6 — Labels that mean nothing to a new reader

"Legacy feature" (E1–E5 table heading), "Readiness basis", "release impact", "Spec readiness",
"Candidate scope readiness".

**Fix:** "Delivered", "Why not ready" (if kept), and drop the release-page readiness columns.

## 7. Other issues

### O1 — The published review still says the refactor is not implemented

`plans/reviews/docs-structure-review.md` is built and searchable. It is not in nav, but search finds
it. Its header says "proposed refactor, not implemented", F4 says "Root strict documentation build
currently fails", and it contains "Implementation instructions for a smaller model".

**Fix:** add a one-line banner ("Implemented in `472bfa4`; kept as evidence"), or exclude
`plans/reviews/` from the site like the archive.

### O2 — Owner answers are recorded but cannot be traced

The ledger says "Owner answers fix Q1–Q3 and Q6–Q8", each marked "Owner answer, 2026-09-23".
ADR-0007 says the owner accepted on 2026-09-24. The review offered those answers as defaults for
the implementer, not as answers. If the owner did answer, the ledger should say where. If not, the
rows should say "review default adopted", and Q6 in particular ([L2](#l2-model-conventions-were-weakened-from-normative-to-advisory-high-needs-owner-decision))
needs a real answer.

### O3 — `auth-overview.md` survives as an orphan page

It is not in nav, but it is still built. ADR-0007 and Q8 allow forwarding pages only for known
external handoff paths. Kiln does not reference this one.

**Fix:** delete it, and add a ledger row saying so.

### O4 — Stale lines in the history area

`plans/_structure.md` says plans "will move to `archive/` in Batch 3". `plans/context.md` has
`**Status:** done` although it is a frozen ledger, not work.

### O5 — The root README was not updated

`README.md`'s last section names five packages' docs; FastAPI and SQLAlchemy are missing. It does
not route to the new docs areas (board, ADRs, architecture). Kiln's rule is that README, CLAUDE and
AGENTS link to the tree rather than describe it.

### O6 — The development guide copies `CLAUDE.md`

`guides/development.md` repeats the command table from `CLAUDE.md`. One of them will drift.

**Fix:** the guide owns the commands. `CLAUDE.md` links to it and keeps only its agent-specific
constraints.

### O7 — Nav mixes packages and maintainer areas

The root nav lists the seven packages first, then Architecture…History. The review proposed "Home;
Packages (seven includes); Architecture; …". A "Packages" section would make the maintainer areas
visible without scrolling past seven package trees.

### O8 — The removed-symbol grep was applied too literally

See [L6](#l6-a-normative-line-in-the-api-conventions-was-changed-to-pass-a-grep-medium) and
[L7](#l7-strictdataclassmixin-is-recorded-as-removed-but-it-exists-medium). Future checks should
say "no current page describes X as present", not "X does not appear".

### O9 — Local docs builds need a patched Python 3.14

The container's Python 3.14.0rc2 makes the `mkdocstrings` pydantic config fail
(`_eval_type() got an unexpected keyword argument 'prefer_fwd_module'`), so every strict build exits
1. On Python 3.14.7 all eight builds pass. This is an environment issue, not a docs defect.

**Fix:** state a minimum patch release in `guides/development.md`, or pin one in
`.python-version`.

### O10 — The web adoption index now calls the FastAPI page a "Pointer"

Fine on its own. But `guides/quickstart.md` sends FastAPI readers to "the FastAPI package pointer",
a page whose only content is "go elsewhere". Name the `rn-forge-fastapi` wiring guide directly: a
package-name reference, which the standalone-build rule allows.

## Questions for the owner

| ID | Question | Why it matters |
| --- | --- | --- |
| AQ1 | Did you answer review Q1–Q3 and Q6–Q8, or did codex adopt the defaults? | Decides whether ADR-0007 is accepted, and whether the model-conventions rewrite ([L2](#l2-model-conventions-were-weakened-from-normative-to-advisory-high-needs-owner-decision)) stands. |
| AQ2 | Did you ask for the "Readiness" axis? If not, may we replace it with kiln's `elaborating` status? | Drives [S1](#s1-a-second-status-axis-readiness-was-invented-high-needs-owner-decision) and most of the tone fixes. |
| AQ3 | Model conventions: keep them advisory, or restore the normative vocabulary as a deferred spec? | [L2](#l2-model-conventions-were-weakened-from-normative-to-advisory-high-needs-owner-decision) |
| AQ4 | Kiln's web cells need resolvable pins now: cut `commons`/`web` tags early, or pin the web packages to `feature/upgrade` until the stable release? | [B1](#b1-kilns-live-blocker-on-resolvable-pins-is-not-recorded-high), [D4](#d4-adr-0002-leaves-out-the-interim-branch-rule-medium), [R3](#r3-the-release-trigger-ignores-kilns-live-need-high) |
| AQ5 | Should done epics get per-row feature IDs so release-1 can list scope? | [S2](#s2-done-epics-have-no-feature-ids-medium), [R4](#r4-done-epics-cannot-be-selected-as-release-scope-medium) |
| AQ6 | Keep release-1 as a placeholder, or remove it until scope is selected (kiln's rule)? | [R1](#r1-release-1-was-cut-before-it-had-scope-medium) |
| AQ7 | Which of the candidate ADRs in [D6](#d6-durable-decisions-with-no-adr-medium) do you want? | Scope of the ADR work. |

## Proposed order of work

1. **Restore lost content.** L1 (archive the handoff, restore its design sections), L3 (feature
   designs), L6 (API conventions line), L7 (StrictDataclassMixin records). These are mechanical
   and need no decisions.
2. **Record the kiln blocker.** B1 and B5, after AQ4.
3. **Settle the spec model.** AQ2 and AQ5, then S1–S10, R1, R4 and B2 in one pass. They touch the
   same pages.
4. **Fix the release mechanics text.** R2, R6, S9, and D4 after AQ4.
5. **ADRs.** D1–D7, after AQ1 and AQ7.
6. **Tone pass.** W1–W6 across the spec, release and index pages. Do this last, because the
   earlier steps rewrite most of those pages anyway.
7. **Small fixes.** L8–L10 and O1–O10.

## Verification record

All commands ran on 2026-09-25 against `472bfa4`.

| Check | Result |
| --- | --- |
| Archived plans vs `12da7f3` (`diff`, per file) | Ten plans, the board and the survey differ only by the banner and relative-link edits. |
| Ledger row count | 309 rows, matching the page's claim. |
| `mkdocs build --strict`, root and seven packages, Python 3.14.0rc2 | All exit 1: mkdocstrings/pydantic incompatibility with the rc interpreter ([O9](#o9-local-docs-builds-need-a-patched-python-314)). |
| Same, Python 3.14.7 (separate environment in the scratchpad) | All eight exit 0. No warnings and no anchor INFO lines. Archive and `_structure.md` files absent from output and search. |
| Remote tags (`git ls-remote --tags origin`) | `rn-forge-commons` v0.1.0–v0.2.2 and `rn-forge-django` v0.1.0–v0.2.2 only. |
| Manifests vs release-1 matrix | Versions, base edges and extra edges match. |
| `.importlinter` | Eight contracts, as `architecture/workspace.md` says. |
| Source checks | No redaction module in commons and no `sse` extra (F6.1/F6.2 unbuilt, correct). `Operation` exists (C5 correct). No batch/undelete/readMask handlers (E13 correct). `StrictDataclassMixin` exists ([L7](#l7-strictdataclassmixin-is-recorded-as-removed-but-it-exists-medium)). |
| Commit hashes cited in E1–E5, ADR-0005, ledger | All exist; subjects match their claimed content. The `-S` history search places `FastApiApp` and `unmapped_exceptions` in `373d6bc`. |
| Kiln `feature/v1` | Board, E5, E7 and `plans/context.md` read for pykit references; see B1, B5 and L1. |
