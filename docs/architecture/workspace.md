# Workspace boundaries

This page shows how the seven pykit packages depend on each other. It is for maintainers choosing where a shared contract or adapter belongs.

**Status:** done

**Owner:** pykit.

## Package graph

| Package | Import path | Direct pykit dependencies in its manifest | Responsibility |
| --- | --- | --- | --- |
| `rn-forge-commons` | `rn_forge.commons` | None | Runtime-neutral utilities, protocols, logging and process output |
| `rn-forge-cli` | `rn_forge.cli` | `rn-forge-commons` | Generic Typer application and declared `[cli]` commands |
| `rn-forge-tooling` | `rn_forge.tooling` | `rn-forge-commons`, `rn-forge-cli` | Generation, local state, templates, installation and documentation mechanics |
| `rn-forge-web` | `rn_forge.web` | `rn-forge-commons[pydantic]` | Framework-neutral HTTP contracts and conformance cases |
| `rn-forge-django` | `rn_forge.django` | `rn-forge-commons`, `rn-forge-web` | Django and Django REST framework adapters |
| `rn-forge-fastapi` | `rn_forge.fastapi` | `rn-forge-web[security]`; `rn-forge-commons[excel]` with the `transfer` extra | FastAPI adapters |
| `rn-forge-sqlalchemy` | `rn_forge.sqlalchemy` | `rn-forge-web` | Async SQLAlchemy models, upsert and keyset pagination |

The framework packages are siblings over `rn-forge-web`. The CLI and tooling branch is separate from the HTTP branch. Optional extras add capabilities at the owning package; for example, Django's `oidc` extra adds commons and web auth dependencies.

## Executable boundaries

The root `.importlinter` file defines eight contracts. It forbids `rn_forge.commons` from importing the CLI and tooling layers, and forbids `rn_forge.cli` from importing tooling. It keeps `rn_forge.web` free of Django, FastAPI, Starlette and the developer-tool layers. It also keeps Django, FastAPI and SQLAlchemy independent of each other. Framework code generation may import tooling only from its optional `codegen` subpackage; the generators are [deferred](../specs/epics/E11-framework-codegen/index.md).

All seven packages require Python 3.14 or later and provide typed package markers. They have independent versions and [pinned git-tag dependencies](../releases/index.md). The root workspace overrides those dependencies to local members for development. That override does not prove that the intended tags install outside the workspace.

Package guides own API details: [commons](../rn-forge-commons/index.md), [CLI](../rn-forge-cli/index.md), [tooling](../rn-forge-tooling/index.md), [web](../rn-forge-web/index.md), [Django](../rn-forge-django/index.md), [FastAPI](../rn-forge-fastapi/index.md), and [SQLAlchemy](../rn-forge-sqlalchemy/index.md). The [package selection guide](../guides/choosing-packages.md) starts from an application's needs.
