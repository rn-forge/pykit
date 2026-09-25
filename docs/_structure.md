# Root documentation routing

This file tells maintainers where to put root documentation. [The reader index](index.md) links to the published pages; each area's `_structure.md` gives its admission rules.

## Areas

| Area | Holds |
| --- | --- |
| `architecture/` | Current package relationships and cross-package behavior. |
| `guides/` | How to choose, combine and develop with the packages. |
| `runbooks/` | Repeated maintainer procedures with decisions or gates. |
| `releases/` | Coordinated package-batch scope and release evidence. |
| `specs/` | Work, acceptance, status and open questions. |
| `adr/` | Durable architectural decisions. |
| `plans/` | Source plans, review evidence and the migration ledger. |

Installed-package usage stays in that package's README, guides and API pages. The web adoption pack stays with `rn-forge-web`. Agent working rules stay in `CLAUDE.md`; `AGENTS.md` remains its pointer.

Root MkDocs navigation is maintained manually. `_areas.yml` records the intended area order; it does not generate nav or enforce structure. The root site excludes routing files and raw archives. The seven package sites still build independently.
