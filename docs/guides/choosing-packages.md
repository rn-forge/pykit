# Choosing packages

This guide helps application authors select pykit packages. Each package's own guide explains its setup and API.

| Need | Start with | Add when needed |
| --- | --- | --- |
| Runtime utilities, configuration, logging or process output | [`rn-forge-commons`](../rn-forge-commons/index.md) | Its named extras for integrations |
| A batch command or declared command-line application | [`rn-forge-cli`](../rn-forge-cli/index.md) | `rn-forge-tooling` for generation, managed files or tool installation |
| A developer tool that installs itself or manages generated files | [`rn-forge-tooling`](../rn-forge-tooling/index.md) | Its tooling-owned `[lifecycle]` surface |
| HTTP contracts shared across frameworks | [`rn-forge-web`](../rn-forge-web/index.md) | A framework adapter for application wiring |
| A Django service | [`rn-forge-django`](../rn-forge-django/index.md) | Django extras such as `drf`, `oidc`, `fixtures` or `celery` |
| A FastAPI service | [`rn-forge-fastapi`](../rn-forge-fastapi/index.md) | `oidc` or `transfer` extras |
| Async SQLAlchemy models and persistence helpers | [`rn-forge-sqlalchemy`](../rn-forge-sqlalchemy/index.md) | The web contract it already depends on |

Use `rn-forge-web` for shared wire behavior. Django and FastAPI bind that behavior to their frameworks. SQLAlchemy is a sibling persistence package; it does not define a common object-relational mapping layer for the adapters. Application code imports `rn_forge.web` directly alongside its adapter, because the adapters do not re-export it ([ADR-0002](../adr/ADR-0002.md)). Declare `rn-forge-web` next to the adapter, at the tag the adapter release pins, rather than relying on it arriving transitively. See the [workspace graph](../architecture/workspace.md) for direct dependencies and import boundaries.

Consumers pin pykit packages to git tags ([ADR-0004](../adr/ADR-0004.md)). The [release pages](../releases/index.md) record which tags exist. A workspace source override resolves local members during development only.
