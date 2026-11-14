# E22 — Pykit simplification

|  |  |
| -- | -- |
| **State** | New |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F22.1 — Short specs with stable work records](F22.1-specs.md) | New | release-9 | 2 New |
| [F22.2 — One current explanation per audience](F22.2-documentation.md) | New | release-9 | 2 New |
| [F22.3 — Behavioral tests and performance baselines](F22.3-tests-and-measurements.md) | New | release-9 | 3 New |
| [F22.4 — Commons with explicit side effects](F22.4-commons.md) | New | release-9 | 5 New |
| [F22.5 — CLI invocation state with a clear lifetime](F22.5-cli.md) | New | release-9 | 2 New |
| [F22.6 — Installer transactions with honest recovery](F22.6-tooling.md) | New | release-9 | 3 New |
| [F22.7 — HTTP policy with bounded readiness](F22.7-web.md) | New | release-9 | 3 New |
| [F22.8 — Auth policy and bounded caches](F22.8-auth.md) | New | release-9 | 4 New |
| [F22.9 — Django adapters with safe parsing and ownership](F22.9-django.md) | New | release-9 | 3 New |
| [F22.10 — FastAPI adapters with clear validation boundaries](F22.10-fastapi.md) | New | release-9 | 3 New |
| [F22.11 — SQLAlchemy bulk work with explicit bounds](F22.11-sqlalchemy.md) | New | release-9 | 2 New |
| [F22.12 — Tabular helpers without redundant copies](F22.12-data.md) | New | release-9 | 2 New |
| [F22.13 — Small release utilities with one metadata path](F22.13-devops.md) | New | release-9 | 2 New |

<!-- END derived features -->

Simplify the existing ten packages, their tests and documentation. Give shared
policy one owner, remove redundant work, and keep framework adapters focused on
translation. Correctness defects found during the review get regression cases
before refactoring. Performance work starts with measurements and preserves the
observable contract unless a separate decision explicitly changes it.

The [review and proposed design](design.md) explains the evidence, priorities,
tradeoffs and measurement plan. Features are in
[Release 9](../../../releases/release-9/index.md); implementation is limited to
its stories, and the epic authorizes no dependency addition, publishing or
history rewrite.

## Order

1. F22.3 establishes behavioral coverage and representative measurements.
1. Fix the correctness cases in each affected package before moving its code.
1. F22.4 to F22.13 simplify packages independently. Shared HTTP policy in F22.7
   and identity policy in F22.8 precede their adapter changes in F22.9/F22.10.
1. F22.2 updates consumer documentation with each package change. F22.1 cuts
   settled spec prose after those changes, preserving unfinished work.

A decision story is settled with the owner before the stories that depend on it.
A build story gets its brief, `_briefs/<story>.md`, when it is next, so each
brief is written against current code. A contract settled while writing a brief
goes into the story's acceptance, because the brief is deleted when the story
closes.

## Scope constraints

- Keep published package boundaries, optional extras and curated facades. A
  source move within a package must preserve supported imports; a move across
  packages follows ADR-0002 and has no compatibility alias.
- Keep RFC wire behavior, security controls, denied-path tests, transaction
  guarantees and standalone package installs. An intentional behavior change
  needs its own regression test, changelog entry and versioning assessment.
- Do not reopen deferred Azure, codegen, messaging, fixtures, Celery or queue
  work, or promote parked ideas. E15's deferred extractions stay there.
- Generated tasks, workflows and routing rules remain kiln-owned. Any desired
  change to their contract is a separate upstream request, not an in-place
  edit.
- Preserve permanent IDs, closed work and shipped release records. No squash,
  branch deletion, retagging or replacement of the existing epic inventory.

## Completion

Each feature supplies observable acceptance below. Package changes pass the
narrow relevant tests, formatting, typing and import checks through `task`; the
completed epic passes `task validate`. The performance comparison names inputs,
environment, time, peak memory and operation counts; it makes no unmeasured
speedup claim. Documentation generation is idempotent and all eleven sites build
strictly through `task docs:build`.

## Considered and rejected

- A package split or a universal adapter framework as the default cleanup.
  Neither follows from file size or duplicated syntax alone.
- A fixed line-count or percentage reduction target. It rewards relocating
  complexity and deleting useful contracts; acceptance follows behavior and
  eliminated duplication instead.
- Rewriting specs into a new taxonomy or squashing repository history. Existing
  IDs, unfinished features and released packages make this a separate
  decision.
