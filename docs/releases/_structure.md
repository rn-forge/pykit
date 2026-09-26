# releases/ — what belongs here

## Belongs here

- One page per coordinated release, `release-<n>/index.md`: its `**Status:**` (`planned`, `in progress`, or `shipped` with the date), entry criteria, scope and exit criteria, and, once shipped, the tags and install evidence.
- Scope named by story ID, linking to the feature that holds the story. Done epics that predate the story taxonomy are named by feature ID, and the page says so.

## Does not belong here

| Instead of | Put it in |
| --- | --- |
| A story's text, acceptance, design or status | its feature under `specs/` |
| Why a choice was made | an ADR under `adr/` |
| How to run a release | `runbooks/releasing-packages.md` |

## Naming and shape

- `release-<n>/index.md`; the area `index.md` lists them, newest first.
- A story belongs to one release at a time, and that assignment lives only on the release page.
- Each package keeps its own version and tag ([ADR-0004](../adr/ADR-0004.md)). A release coordinates packages; it is not one pykit version.

## Changing this area

1. Cut a release page when there is scope to put on it.
1. Give it its status, entry criteria, scope as IDs linking to their features, and exit criteria. Nothing else.
1. List it in `index.md`, newest first.

Moving a story between releases edits the release pages and nothing else. A release is `shipped`, with the date, once its exit criteria hold.
