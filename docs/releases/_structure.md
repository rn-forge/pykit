# releases/ — what belongs here

## Belongs here

- One page per release, `release-<n>/index.md`, in this order:
    - `**Status:**`: `planned`, `in progress` or `shipped`, with the date.
    - **Entry criteria**: what must hold before work on the release starts.
    - **Scope**: a table of the features picked from the backlog, one row each:
      the feature linked to its spec, its epic, and its status. Done epics that
      predate the story taxonomy, and other done work the release carries, go in
      a `### Done before this release` table under it: epic, what it delivered,
      and its implemented dates.
    - **Decisions**: each ADR the release added or updated, linked, with one line
      on what changed.
    - **Breaking changes**: what a consumer must change on upgrading, or `None`.
    - **Progress**: a few lines on what is next and what blocks it.
    - **Commits**: the `git log --grep` command that lists commits naming a scope
      ID, and its output, refreshed at least at the cut.
    - **Exit criteria**: what must hold for the release to ship.
    - **Shipped**: once shipped, the release evidence — each version and tag, its
      commit, and what was checked.

## Does not belong here

| Instead of | Put it in |
| -- | -- |
| A story's text, acceptance, design or status | its feature under `specs/` |
| Why a choice was made | an ADR under `adr/` |
| How to run a release | `runbooks/` |

## Naming and shape

- `release-<n>/index.md`; the area `index.md` lists them, newest first.
- A feature belongs to one release at a time, and that assignment lives only on
  the release page.
- The scope table's status column mirrors each feature's own `**Status:**` line,
  so the release's state reads without opening every feature. Update both in
  the commit that changes the feature's status.
- Commit subjects name the story or feature IDs they deliver, so the commits
  section can be regenerated.

## Changing this area

1. Cut a release page when there is scope to put on it, not ahead of time.
1. Fill the sections above. List it in `index.md`, newest first.
1. Add or remove scope rows as the plan changes; a moved feature leaves one
   release page and joins another.

A release is `shipped`, with the date, once its exit criteria hold.
