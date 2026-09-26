# plans/ — what belongs here

## Belongs here

- `context.md`: the ledger mapping every old plan section, phase, D-number and R-item to its current home, with the conflicts found.
- `archive/`: the old plans and rewritten pages, frozen, each with a one-line historical banner. Excluded from the site.
- `reviews/`: review evidence, each with a banner saying whether it was applied. Excluded from the site.

## Does not belong here

| Instead of | Put it in |
| --- | --- |
| Live work and status | `specs/` |
| A decision | `adr/` |
| Current usage | package docs or root `guides/` |

## Changing this area

Archived files are evidence, not instructions, and are never edited after archiving. Before `archive/` or `reviews/` is deleted, record in `context.md` the last commit that holds them, so every `Source:` line stays retrievable with `git show <commit>:<path>`. When a current page is rewritten and its old content would otherwise survive only in Git, archive the old text and add a ledger row.
