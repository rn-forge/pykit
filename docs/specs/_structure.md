# specs/ — what belongs here

## Belongs here

- Every piece of pykit work as an epic, `epics/E<n>-<slug>/index.md`, done work included.
- A feature of an unfinished epic as `F<n>.<m>-<slug>.md` beside it, holding its stories inline as `S<n>.<m>.<k>` headings, each with its own `**Status:**` and `**Acceptance:**`.
- A done epic that predates this taxonomy keeps its features as numbered rows in its index, each with the commits that delivered it.
- Design for unbuilt work, in the feature's `## Design`.
- Open questions, in `## Open questions` on the epic or feature they block.
- Work that is real but not scheduled, as a `deferred` epic or feature with entry criteria. Its items are numbered rows until promoted.
- Ideas not yet agreed as work, in `backlog.md`: a row each (slug, one-line summary, source), with a `##` section under the table only when there is more to record. Entries take no ID and no status.

## Does not belong here

| Instead of | Put it in |
| --- | --- |
| Behavior that already exists | `architecture/` or the package's docs |
| A decision | an ADR under `adr/` |
| Which features ship in which release | `releases/`, which links here |
| History and evidence | the commit message |

## Naming and status

- IDs are permanent. Never renumber; a moved story keeps its ID; gaps are fine. Work that is no longer needed is removed and its ID is never reused: a retired story is listed on its feature's `**Retired:**` line, a retired epic on the board.
- Epic and feature status is one of these:

| Status | Means |
| --- | --- |
| `elaborating` | Agreed, but its stories or design are not settled. |
| `planned` | Stories written; ready to be picked for a release. |
| `in progress` | At least one story started. |
| `done` | Every story's acceptance holds; carries an `**Implemented:**` date and commits. |
| `deferred` | Not scheduled; carries `**Entry criteria:**`. |

- Story status is `planned`, `in progress` or `done (<date>)`. A story in a deferred feature is `deferred`.
- `done` means implemented. It does not mean a package tag exists; releases record tags.
- Status lines appear only on epics, features, stories and releases.
- `**Source:**`, when present, cites a current document or the owner decision and its date.

## Changing this area

**Parking an idea:** add a row to `backlog.md`, and a section linked from the row if it needs more than a line. Do not elaborate a backlog entry unless the owner asks.

**Adding work:**

1. Take the next free ID. An idea promoted from the backlog carries its section into the new file, and its entry is deleted.
1. Create the epic or feature with its status: `elaborating` until it has stories, `deferred` with entry criteria if it is not scheduled.
1. Put design in the feature's `## Design`, and link to `architecture/` for current behavior.
1. Add the epic's row to the board in `index.md`, in exactly one group.

**Writing acceptance:**

- A story's `**Acceptance:**` lists observable results, including the tests that prove it. Every result is checkable inside this repository; when it needs a host application, a test scaffolds one ([ADR-0008](../adr/ADR-0008.md)).
- A decision the work needs is its own story, so other work can depend on the decision alone.
- A feature with several stories has a `## Acceptance` block that tags each line with the story it proves. A one-story feature keeps its acceptance on the story.
- Where a line can be scripted, the block is a shell script that starts with `set -euo pipefail` and never turns a failure into output. A negative check uses `absent`, not a bare `! cmd`. What cannot be scripted, such as an approval, is listed under the block.

```bash
absent() { local rc=0; rg -q --hidden --glob '!.git' "$@" </dev/null || rc=$?; [ "$rc" -eq 1 ]; }
```

**Closing work:** a story is done when its acceptance holds. When every story is done, set the feature and then the epic to `done` with the `**Implemented:**` line, update the feature's row on its release page, and move the board row. An answered open question becomes an ADR, or a rejected option under *Considered and rejected*; then remove the question.

**Checking removed behavior:** a check that a removed symbol is gone asks "does any current page describe it as present?", not "does the name appear?". A page may name removed behavior to say it is gone.
