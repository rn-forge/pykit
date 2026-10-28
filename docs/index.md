# pykit

`pykit` is a uv workspace of ten independently versioned `rn-forge-*` Python
packages. Start with a package for its usage guides, or use the root guides to
combine packages.

| Package | Use it for |
| -- | -- |
| [rn-forge-commons](rn-forge-commons/index.md) | Runtime-neutral utilities, protocols and logging. |
| [rn-forge-cli](rn-forge-cli/index.md) | Generic command-line applications. |
| [rn-forge-tooling](rn-forge-tooling/index.md) | File-owning generation, installation and tool lifecycle work. |
| [rn-forge-web](rn-forge-web/index.md) | Framework-neutral HTTP contracts and conformance cases. |
| [rn-forge-auth](rn-forge-auth/index.md) | Authentication and authorization primitives: identity and authorization-context contracts, `Principal`, `Requirement`, stores, the login flow and local providers; OIDC and OAuth 2.0 login and the OIDC token profiles behind an extra. |
| [rn-forge-django](rn-forge-django/index.md) | Django and Django REST framework adapters. |
| [rn-forge-fastapi](rn-forge-fastapi/index.md) | FastAPI adapters and application assembly. |
| [rn-forge-sqlalchemy](rn-forge-sqlalchemy/index.md) | Async SQLAlchemy models, upsert and keyset pagination. |
| [rn-forge-data](rn-forge-data/index.md) | Excel and tabular data helpers; a pandas adapter behind an extra. |
| [rn-forge-devops](rn-forge-devops/index.md) | CI and release automation for rn-forge repositories in any language, run with uv. |

For package choice and relationships, read
[choosing packages](guides/choosing-packages.md) and
[workspace boundaries](architecture/workspace.md). The package guides provide
auth setup steps.

Maintainers can start with the [work index](specs/index.md),
[decisions](adr/index.md), [release coordination](releases/index.md), or
[runbooks](runbooks/index.md).
