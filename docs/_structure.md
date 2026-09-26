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

Installed-package usage stays in that package's own `docs/`: `index.md`, `guides/`, a generated `reference/` and `changelog.md`, which includes the package's `CHANGELOG.md`; the same shape as a single-package repository. The package README is its landing page on an index, so every link in it is absolute ([ADR-0009](adr/ADR-0009.md)). Agent working rules stay in `CLAUDE.md`; `AGENTS.md` remains its pointer.

This tree follows the shared rn-forge docs standard ([ADR-0007](adr/ADR-0007.md)). Root MkDocs navigation is maintained manually and includes the seven package sites; `_areas.yml` declares the areas in nav order. The root site excludes routing files, the raw archive and the review evidence. The seven package sites still build independently.
