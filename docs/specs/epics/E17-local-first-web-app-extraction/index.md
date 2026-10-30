# E17 — Local-first web-app extraction

|  |  |
| -- | -- |
| **State** | New |

Apollo, a local-first FastAPI music-library application, wrote several pieces of
generic plumbing that any single-user FastAPI tool would write again: problem
rows built from a domain exception hierarchy, a single-owner thread for a
library that is not thread-safe, a per-item failure capturing parallel map,
SQLite engine and migration setup, safe filesystem mutation helpers, and a
durable in-process job queue. This epic moves them into the packages that
already own their neighbours. Each feature ships alone.

Apollo's rebuild proceeds on the pins it has today and does not wait for any of
this. It adopts each piece after the feature is released and the application's
pinned `rn-forge-*` tags are bumped; until then it keeps its own copy.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F17.1 — Problem rows from an exception hierarchy](F17.1-problem-rows-from-exceptions.md) | `ProblemRegistry.register_hierarchy`, a guide recipe that keeps lookup errors from bugs at 500, and a default 5xx log sink for `AppConfig.log`. | New |
| [F17.2 — Single-owner thread actor](F17.2-thread-actor.md) | `ThreadActor[R]` in `rn-forge-commons`: one owner thread builds and uses a resource that is not thread-safe. | New |
| [F17.3 — `TaskPool.map_settled`](F17.3-taskpool-map.md) | Per-item failure capture, in input order, on the pool's executor, without `Task` subclasses. | New |
| [F17.4 — SQLite engine and embedded migrations](F17.4-sqlite-engine-migrations.md) | An async `create_sqlite_engine` and `run_migrations` in `rn-forge-sqlalchemy`. | New |
| [F17.5 — Safe filesystem mutation](F17.5-safe-fs-and-tool-probe.md) | `atomic_replace`, `move_no_clobber` and `prune_empty_parents` in `rn-forge-commons`. | New |
| [F17.6 — Durable in-process job queue](F17.6-durable-job-queue.md) | An async SQLite-backed job worker, context, models and SSE delta helper. Design sketch only. | New |

[F17.6](F17.6-durable-job-queue.md) is tagged `deferred`; its entry criterion is
that a second application needs the queue.

## Context

Placed as its own epic, not in [E6](../E6-consumer-reuse/index.md). E6 is tagged
`deferred` as a whole and is scoped to two named pieces of plumbing, each in one
package, that several applications had already written; its entry criterion is
the owner scheduling either of those two. These features span four packages,
come from one application's review, and are not deferred, so putting them under
E6 would either make them wait on E6's criterion or force E6 to lose its tag.
[F17.6](F17.6-durable-job-queue.md) builds on
[F6.2](../E6-consumer-reuse/F6.2-sse.md) and links to it.

## Considered and rejected

- **One feature for the whole epic.** The features touch different packages, and
  an application can want the thread actor without the SQLite helpers.
- **A new `rn-forge-local` package.** Each piece belongs beside what it extends:
  the registry in `rn-forge-web`, the runtime helpers in `rn-forge-commons`,
  the engine in `rn-forge-sqlalchemy`. A package of leftovers would duplicate
  their boundaries ([ADR-0001](../../../adr/ADR-0001.md)).
- **Typed application state** is not agreed work yet; it is parked in the
  [ideas list](../../ideas.md#typed-application-state).
- **Single-consumer conveniences:** a worker-count helper, a `default_registry`
  keyword for lookup errors, and tool-version probing. Each is a line or two
  in the application, or a heuristic only Apollo needs; see
  [F17.1](F17.1-problem-rows-from-exceptions.md),
  [F17.3](F17.3-taskpool-map.md) and [F17.5](F17.5-safe-fs-and-tool-probe.md).
