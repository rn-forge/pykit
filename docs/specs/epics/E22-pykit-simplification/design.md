# Pykit simplification — review and proposed design

This proposal covers the existing packages, tests and documentation. Each
feature settles its own implementation; F22.3 establishes measurement and
behavioral coverage first. The findings below are static source observations,
not executed defect reproductions or measured speedups. The feature acceptance
requires reproductions before fixes and measurements before optimizations.

## Review boundary

The review used the ten packages' source, representative tests, manifests,
facades and docs, together with root architecture, ADRs, release/spec status,
scaffold fixtures and generated task definitions. It looked for duplicate
policy, implicit global state, unnecessary allocation, unbounded retention,
fragile failure handling and tests tied to implementation. It was not an
exhaustive security audit or a dependency/library evaluation.

The simplification principles are: tests exercise contracts rather than source
layout; each fact has one owner; composition passes policy into adapters; and
large files split by responsibility only when that reduces coupling. Repository
history and spec IDs remain intact. No other repository's internal milestones or
spec IDs become acceptance criteria here.

Existing constraints remain authoritative: [ADR-0001](../../../adr/ADR-0001.md),
[ADR-0002](../../../adr/ADR-0002.md), [ADR-0003](../../../adr/ADR-0003.md) and
[ADR-0011](../../../adr/ADR-0011.md). This proposal does not select a new
library, authorize a new package or relax security controls.

## Scale and where it matters

Counts are a review baseline, measured from Python source/tests and Markdown
files at `637a7df`, on 2026-11-14. Lines include comments and blank lines; words
are whitespace-delimited. Generated reference pages count as docs files. They
identify review effort, not complexity thresholds or deletion targets.

| Package | Source files / lines | Test files / lines | Docs pages | Concentrated responsibilities |
| -- | -- | -- | -- | -- |
| commons | 43 / 9,620 | 33 / 8,583 | 45 | Logging 1,138 lines; collections 827; documents 814 |
| cli | 4 / 574 | 5 / 608 | 10 | Invocation/global state; declarative option/error paths |
| tooling | 9 / 1,298 | 4 / 701 | 8 | Installer lifecycle 435; CLI lifecycle 310 |
| web | 22 / 5,862 | 20 / 3,444 | 29 | Conformance cases 1,890; problem rendering 652 |
| auth | 19 / 4,377 | 28 / 4,401 | 28 | OIDC 1,538; testing support 619 |
| django | 69 / 8,066 | 50 / 10,202 | 39 | Transfer 698; auth routes 591; view mixins 522 |
| fastapi | 23 / 4,680 | 26 / 7,922 | 28 | Transfer 936; auth routes 725; sessions 504 |
| sqlalchemy | 7 / 679 | 9 / 1,475 | 9 | Upsert read/classify/write and count semantics |
| data | 3 / 697 | 4 / 662 | 7 | Excel 409; pandas 279 |
| devops | 4 / 268 | 2 / 149 | 6 | Requirement policy coverage, not module size |

Specs contain 116,546 words in 104 files, versus 747 architecture words, 1,794
guide words, 1,952 runbook words and 7,461 release words. The large auth design,
Sonar ledger and cutover brief warrant a retention pass. This does not establish
that every spec paragraph should move into a guide.

Only nine test function names carry story-like prefixes, in
`commons/tests/fs/test_blocks.py`; no Python source files contain dotted spec
IDs under the inventory's ID pattern. A repository-wide test rename is therefore
unjustified. Source inspection in auth conformance and facade tests can enforce
real architecture/security rules and is not automatically test fragility.

## First fix correctness and recovery

Paths below are relative to
`packages/rn-forge-<package>/src/rn_forge/<package>/` unless prefixed with
`tests/`. Locations identify the reviewed source and may move during
implementation. Severity is proposed remediation priority, not a claim about
production incident frequency.

| Priority | Evidence | Failure or contract gap | Owner |
| -- | -- | -- | -- |
| High | tooling `install/lifecycle.py:234-280` | One failing undo aborts later recovery; final work-directory deletion can remove the displaced working install | F22.6 |
| High | django `drf/idempotency.py:54-58` | Expiry between failed atomic add and get returns the execute sentinel without owning the claim | F22.9 |
| High | web `health.py:230-239` | Executor context shutdown waits for blocked work, defeating response timeout; relative waits extend later deadlines | F22.7 |
| High | commons `logging/logger.py:562-575,957-965` | Logger retrieval overwrites a consumer record factory; import-time retrieval makes this an integration side effect | F22.4 |
| Medium | auth `context_cache.py:128-146` | Expiry checks reuse but never evict entries for accounts no longer accessed | F22.8 |
| Medium | cli `options.py:135-141`, `app.py:162-168` | Quiet/JSON persists into later invocation; idempotent logger initialization can ignore later log-level/file options | F22.5 |
| Medium | django `drf/pagination.py:43` | `--1` and `²` pass the predicate but fail integer conversion instead of forgiving invalid page size | F22.9 |
| Medium | django `models/cache.py:48-70` | Delimiter-joined composite keys collide: `(a.b, c)` and `(a, b.c)` | F22.9 |
| Medium | fastapi `idempotency.py:66-72` | JSON decoding happens before safe-method bypass and outside validation; Request-only routes can raise unhandled decode errors | F22.10 |
| Medium | data `pandas.py:120` | Truthiness-to-empty-string conversion loses valid zero and False values | F22.12 |
| Medium | commons `generation/artifacts.py:250-252` | `written` includes unchanged, skipped, forgotten, dry-run and duplicate paths despite its byte-change contract | F22.4 |
| Medium | commons `logging/logger.py:616-666,179` | Level-forwarding wrappers add caller frames without adjusting stack level | F22.4 |

These changes alter observed erroneous behavior and must not hide inside a
nominally behavior-preserving file move. Add failing regression cases, fix, then
reorganize. Installer recovery must retain evidence needed to repair a partial
failure. A synchronous timeout must not be described as cancellation: Python
cannot safely stop arbitrary blocked worker code.

The SQLAlchemy count issue is a contract question to reproduce, rather than a
confirmed incorrect returned count in existing tests. `upsert.py:41` promises
exact counts but classifies before the conflict-handling write. Competing
writers can change the database between those operations. F22.11 chooses and
tests the intended count semantics before adding locks or changing SQL.

## Give neutral policy one owner

| Current copies | Proposed ownership | Keep local |
| -- | -- | -- |
| Django `auth/drf/principal.py:114-139`; FastAPI `auth/dependencies.py:109-140` | Auth: account resolution, active-account check, scope limiting and principal projection | Framework exceptions, request extraction and sync/async scheduling |
| Auth `redis.py:176-211`; Django `auth/sessions.py:167-180,223-238` | Auth: SessionInfo record mapping | JSON, cache/session backend and TTL operations |
| Auth `redis.py:67-102`; Django `auth/stores.py:49-80` | Auth: LoginTransaction record mapping | Backend atomic consume/storage |
| Django `auth/rate_limit.py:17-28,65-80`; FastAPI `auth/rate_limit.py:23-34,54-63` | Auth: common window/digest/retry arithmetic if contracts match | Backend atomic increments and async orchestration |
| Tooling `cli/lifecycle.py` verb tuple and command registry | Tooling: derive advertised verbs from its ordered registry | CLI remains ignorant of tooling |
| Root README/package tables, landing page, choosing guide, architecture | One current guide for each decision, short entry summaries | Package guides/reference remain standalone |

Django and FastAPI login completion also repeat account resolution and session
construction (`auth/routes.py:335-375` and `:436-473`). Evaluate extracting only
that pure policy after principal and record mappings work. Do not merge the
route controllers or force synchronous and asynchronous stores into a new
universal abstraction.

CLI/tooling have identical tiny duplicate-name helpers. Removing one copy does
not alone justify a new public commons utility. Consolidate a helper only when
its owning package and supported contract are clear; derive local declarations
and improve malformed-table diagnostics first.

## Reduce work where evidence supports it

| Evidence of work | Experiment before implementation | Constraint |
| -- | -- | -- |
| commons `fs/hashing.py:25` reads whole files; tooling release verification uses it | Large archive digest peak memory/time versus standard-library streaming hashing | Same digest and absent-file behavior |
| data `excel.py:393-396` copies all rows before write-only append | Large dataset export allocation/time with direct iteration | Dataset and output bytes remain in memory; no end-to-end streaming claim |
| data `pandas.py:225-254` writes XLSX bytes then reparses into openpyxl | Compare workbook reuse/direct construction with current formats and cells | Preserve formatting and workbook semantics; reject if complexity outweighs gain |
| commons `runtime/tasks.py:260-263` repeatedly counts names | Submit increasingly large batches; compare a one-pass seen set | Same duplicate detection and order semantics |
| commons `lang/collections.py:430-438` deep-copies override trees again while recursing | Deep/wide config merge allocations and time | No shared mutable branches leak into results |
| auth `stores.py`; FastAPI `auth/rate_limit.py:83-85` sweep dictionaries in common paths | Churn expired entries and concurrent reads; measure lock duration | These development stores do not become a new production backend |
| sqlalchemy `upsert.py:63-81,133-155` retains keyed input, fetched records and full write list | Empty, unchanged, mixed and large upserts; query count and peak memory | Duplicate rejection, audit stamps and caller-owned transactions |
| Root `conftest.py:18-40` builds every wheel for scaffold sessions | Attribute build/setup versus clean install/third-party resolution time | Preserve isolated distribution installation and extra validation |
| Generated `tasks/docs.yml` builds combined and ten standalone sites | Separate parser/build/startup costs and report totals | Keep all strict builds; generated task changes belong upstream |

Set a workload-specific improvement or no-regression target in the measurement
story before selecting an implementation. Use deterministic tests for operation
counts/retention bounds, and comparative measurements for timing/memory. Do not
add flaky wall-clock microbenchmarks to ordinary tests or claim cold imports,
streaming or latency improve because a file got shorter.

## Refactor tests before moving implementation

Concrete starting points:

- `commons/tests/runtime/test_tasks.py:84-103` invokes private `_start` on the
  runner thread; production `_start` renames that thread. Test via submit and
  futures, including a check that the runner's name is unchanged.
- The same test file inserts an impossible orphan into `pool._tasks`
  (`:310-312`). Replace the setup with a reachable public lifecycle or remove
  only the impossible-state branch after proving no production path reaches
  it.
- `cli/tests/test_options.py:26-34` resets global logging/console state between
  tests. Add multi-invocation cases within one test before changing fixtures.
- `auth/tests/oidc/test_verifier.py:149-156` patches a third-party JWKS cache's
  clock through its internal module. Confine unavoidable coupling to support
  code and keep observable key-fetch/acceptance assertions.
- `fastapi/tests/test_sse.py:135-156` uses sleeps to schedule heartbeat
  behavior. Prefer coordinated events and bounded deadlines that retain the
  actual heartbeat/disconnect contract.
- Devops requirement checking spans discovery, groups, URLs and version policy
  in `requirements.py:32-106`; its lone requirements test covers a missing
  ceiling. Add table-driven public contract tests instead of refactoring the
  already small package for symmetry with larger packages.

A helper extraction must retain adapter integration cases. Moving an auth test
into core is not enough to prove cookies, sessions, threadpool boundaries or
framework error responses. Existing service-backed tests must report actual
execution separately from skips; a SQLite pass does not prove PostgreSQL.

## Documentation and work-record retention

F22.1 is intentionally smaller in ambition than a spec reset: preserve IDs,
closed feature records and shipped scope, cut redundant settled build prose, and
route current guidance to its owning docs. Auth's large design page still
contains useful rationale; retain decisions or link to their ADRs rather than
blindly deleting it. Active kiln cutover and index-retirement stories must not
lose their acceptance while waiting on their remaining work.

F22.2 audits root inventories and package entry paths. It also corrects concrete
drift: the scaffold fixture claims sibling requirements are git pins and calls
installs offline even though third-party dependencies resolve from the index;
its `rn-forge-web[drf]` example no longer matches the package graph. The tooling
README recommends direct wrapped tools, conflicting with the task entrypoint.

Shorter pages are not sufficient acceptance. Links, imports, examples, metadata,
generated navigation and combined/standalone strict builds must still work.
Changes to kiln-owned routing or task policy are outside this epic; keep this
plan checkable within pykit using its installed tooling.
