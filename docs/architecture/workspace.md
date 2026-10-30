# Workspace boundaries

How the ten pykit packages depend on each other, and the executable rules that
keep them that way. Read it before placing a shared contract or an adapter.

## Package graph

| Package | Import path | Direct pykit dependencies in its manifest | Responsibility |
| -- | -- | -- | -- |
| `rn-forge-commons` | `rn_forge.commons` | None | Runtime-neutral utilities, protocols, logging and process output |
| `rn-forge-cli` | `rn_forge.cli` | `rn-forge-commons` | Generic Typer application and declared `[cli]` commands |
| `rn-forge-tooling` | `rn_forge.tooling` | `rn-forge-commons`, `rn-forge-cli` | Generation, local state, installation and documentation mechanics |
| `rn-forge-web` | `rn_forge.web` | `rn-forge-commons[pydantic]` | Framework-neutral HTTP contracts and conformance cases |
| `rn-forge-auth` | `rn_forge.auth` | `rn-forge-commons`, `rn-forge-web` | `Principal`, `Requirement`, authenticator and authorizer contracts; OIDC bearer verification behind the `oidc` extra |
| `rn-forge-django` | `rn_forge.django` | `rn-forge-auth`, `rn-forge-commons`, `rn-forge-web`; `rn-forge-data` with the `transfer` and `fixtures` extras | Django and Django REST framework adapters |
| `rn-forge-fastapi` | `rn_forge.fastapi` | `rn-forge-auth`, `rn-forge-web[security]`; `rn-forge-data` with the `transfer` extra | FastAPI adapters |
| `rn-forge-sqlalchemy` | `rn_forge.sqlalchemy` | `rn-forge-web` | Async SQLAlchemy models, upsert and keyset pagination |
| `rn-forge-data` | `rn_forge.data` | `rn-forge-commons` | Excel and tabular data helpers; the pandas adapter sits behind the `pandas` extra |
| `rn-forge-devops` | `rn_forge.devops` | None (third-party `packaging` only) | CI and release automation: the planner core with uv and GitHub Actions adapters |

`rn-forge-auth` sits between `rn-forge-web` and the Django and FastAPI adapters:
it owns the verified caller and the access decision, while `rn-forge-web` keeps
the wire contract. The Django and FastAPI adapters are siblings over
`rn-forge-auth`, and SQLAlchemy is a sibling over `rn-forge-web`. The CLI and
tooling branch is separate from the HTTP branch. `rn-forge-devops` stands apart
from both: it depends on no other pykit package, so a CI run in a repository of
any language installs only `packaging` ([ADR-0012](../adr/ADR-0012.md)).
Optional extras add capabilities at the owning package; for example, Django's
`oidc` extra adds `rn-forge-auth[oidc]`.

## Executable boundaries

The root `.importlinter` file defines fifteen contracts. It forbids
`rn_forge.commons` from importing the CLI and tooling layers, and forbids
`rn_forge.cli` from importing tooling. It keeps `rn_forge.web` free of Django,
FastAPI, Starlette and the developer-tool layers. It layers Django, FastAPI and
SQLAlchemy independently over `rn_forge.auth`, `rn_forge.web` and commons, and
keeps `rn_forge.auth`'s core free of its OIDC adapter. It keeps
`rn_forge.devops` free of every other `rn_forge` package and its core free of
its adapters. It keeps the core of `rn_forge.data` free of its pandas adapter.
Framework code generation may import tooling only from its optional `codegen`
subpackage; the generators are
[deferred](../specs/epics/E11-framework-codegen/index.md). A new package takes
its place in this graph by the placement rules in [ADR-0002](../adr/ADR-0002.md)
and adds its contracts to `.importlinter`.

All ten packages require Python 3.14 or later and provide typed package markers.
They have independent versions and require each other by version range
([ADR-0004](../adr/ADR-0004.md)). The root workspace overrides those
requirements to local members for development. That override does not prove that
the ranges install outside the workspace.

Package guides own API details: [commons](../rn-forge-commons/index.md),
[CLI](../rn-forge-cli/index.md), [tooling](../rn-forge-tooling/index.md),
[web](../rn-forge-web/index.md), [auth](../rn-forge-auth/index.md),
[Django](../rn-forge-django/index.md), [FastAPI](../rn-forge-fastapi/index.md),
[SQLAlchemy](../rn-forge-sqlalchemy/index.md),
[devops](../rn-forge-devops/index.md), and [data](../rn-forge-data/index.md).
The [package selection guide](../guides/choosing-packages.md) starts from an
application's needs.

## Package docs sites

There is no root `reference/` area: each package publishes its own versioned
docs site instead — `index.md`, `guides/`, a generated `reference/` and
`changelog.md` (which includes the package's `CHANGELOG.md`) — the same shape as
a single-package repository ([ADR-0009](../adr/ADR-0009.md)). The package's
`README.md` is that site's landing page, so every link in it is absolute. This
tree follows the shared rn-forge docs standard ([ADR-0007](../adr/ADR-0007.md));
root navigation includes each package site, and the root site excludes routing
files.
