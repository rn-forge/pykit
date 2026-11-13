# Release 8 — kiln adoption and local-first extraction

|  |  |
| -- | -- |
| **Status** | planned |

pykit cuts over onto kiln's `python-lib` archetype (F16.3, then F16.6,
[E16](../../specs/epics/E16-kiln-adoption/index.md)), with every package already
published to PyPI by [Release 7](../release-7/index.md). It also moves Apollo's
generic plumbing into the packages that own its neighbours (F17.1 to F17.5,
[E17](../../specs/epics/E17-local-first-web-app-extraction/index.md)), and adds
log redaction and server-sent events (F6.1 and F6.2,
[E6](../../specs/epics/E6-consumer-reuse/index.md)).

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 7 is shipped.
- For F16.3 and F16.6 only: the work runs first as kiln's S7.2.4 rehearsal from
  kiln `feature/v1`, and the cutover merges once `task kiln:apply` re-renders
  with no change at the configured `[kiln] ref`. kiln F6.7, F6.8 and F6.9 are
  closed.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F6.1 — Structured-log secret redaction](../../specs/epics/E6-consumer-reuse/F6.1-log-redaction.md) | E6 | Closed |
| [F6.2 — Server-sent events](../../specs/epics/E6-consumer-reuse/F6.2-sse.md) | E6 | Closed |
| [F16.3 — Cut over onto kiln](../../specs/epics/E16-kiln-adoption/F16.3-cutover.md) | E16 | Active |
| [F16.6 — Retire the plan outputs generated CI does not read](../../specs/epics/E16-kiln-adoption/F16.6-retire-unread-plan-outputs.md) | E16 | New |
| [F16.7 — Instruction files follow kiln's standard](../../specs/epics/E16-kiln-adoption/F16.7-instructions-follow-kiln-standard.md) | E16 | Closed |
| [F17.1 — Problem rows from an exception hierarchy](../../specs/epics/E17-local-first-web-app-extraction/F17.1-problem-rows-from-exceptions.md) | E17 | Closed |
| [F17.2 — Single-owner thread actor](../../specs/epics/E17-local-first-web-app-extraction/F17.2-thread-actor.md) | E17 | Closed |
| [F17.3 — `TaskPool.map_settled`](../../specs/epics/E17-local-first-web-app-extraction/F17.3-taskpool-map.md) | E17 | Closed |
| [F17.4 — SQLite engine and embedded migrations](../../specs/epics/E17-local-first-web-app-extraction/F17.4-sqlite-engine-migrations.md) | E17 | Closed |
| [F17.5 — Safe filesystem mutation](../../specs/epics/E17-local-first-web-app-extraction/F17.5-safe-fs-and-tool-probe.md) | E17 | Closed |
| [F18.6 — Cache Markdown structure by text](../../specs/epics/E18-kiln-extraction/F18.6-markdown-parse-cache.md) | E18 | Closed |
| [F18.7 — A managed block's end marker can sit at a different indent](../../specs/epics/E18-kiln-extraction/F18.7-managed-block-end-indent.md) | E18 | Active |
| [F21.5 — Retire the self-hosted index](../../specs/epics/E21-pypi-distribution/F21.5-retire-index.md) | E21 | Active |

<!-- END derived scope -->

## Order

1. **F21.5** first, on `feature/release-8`. It retires the self-hosted index
   before the cutover, so the cutover carries no index.
1. **F16.3** as kiln's S7.2.4 rehearsal, on `feature/kiln-cutover`, merged into
   `feature/release-8` once `task kiln:apply` re-renders with no change
   (*revised 2026-11-12:* no longer waits for kiln's `v0.1.0` tag; *revised
   2026-11-13:* merged locally, not by pull request #30). It cuts pykit over
   onto kiln and adds `rn-forge-auth` to the kiln config. kiln must render the
   release behaviour F21.3 built in `main.yml`. S16.3.2 closes on the
   release's run on `main`.
1. **F16.6** after F16.3. It settles whether `plan` keeps the outputs kiln does
   not read.
1. **F17.1, F17.2, F17.3, F17.5, F17.4** do not wait for kiln. F17.2 comes
   before F17.3, whose guide names the actor rule.
1. **F6.1 and F6.2** do not wait for kiln, or for each other.

## Decisions

- Owner decision, 2026-10-29: the kiln cutover (F16.3) and F16.6 move here from
  Release 7, which publishes every package to PyPI so kiln can ship its
  release 1.
- Owner decision, 2026-10-31: F17.1 to F17.5 join this release and F16.3 and
  F16.6 stay, so the release cannot ship until kiln's `v0.1.0` tag exists.
- Owner decision, 2026-11-12: the cutover merges on `[kiln] ref = "feature/v1"`
  once `task kiln:apply` re-renders with no change; the release no longer
  waits for kiln's `v0.1.0` tag.
- Owner decision, 2026-10-31: `alembic` is approved as the only dependency of
  `rn-forge-sqlalchemy[migrations]` (S17.4.1).
- Owner decision, 2026-10-31: F6.1 and F6.2 join this release, and F16.3 and
  F16.6 stay in it.
- Owner decision, 2026-11-03: F21.5 joins this release and lands before F16.3.
- Owner decision, 2026-11-03: S16.3.3 converts the docs to kiln's format on
  `feature/release-8` ahead of `kiln init`, replacing branch
  `feature/kiln-docs-model`.
- Owner decision, 2026-11-13: F16.3's stories close on `feature/kiln-cutover`,
  which merges locally into `feature/release-8` with a merge commit; pull
  request #30 is closed unmerged, and the `feature/release-8` → `main` pull
  request ships the release.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='F16\.[36]|S16\.[36]\.|F21\.5|S21\.5\.|F17\.[1-5]|S17\.[1-5]\.|F6\.[12]|S6\.[12]\.'
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.

## Shipped

Filled at the cut.
