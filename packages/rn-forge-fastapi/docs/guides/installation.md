# Installation

## Install from PyPI

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-fastapi>=0.4,<0.5"]
```

`rn-forge-web` and `rn-forge-commons` come in transitively, each as a version
range. FastAPI comes in as an ordinary PyPI dependency, and pydantic and
Starlette with it. The optional `oidc` extra adds JWKS bearer auth and OIDC login; `redis` adds the
Redis stores the auth binding needs outside development
(`rn_forge.auth.redis` and `rn_forge.fastapi.auth.redis`); `transfer` adds
tabular export and import (`rn_forge.fastapi.transfer`).

## Inside this workspace

`packages/rn-forge-fastapi` is a `uv` workspace member, so the root
`[tool.uv.sources]` overrides the requirement above with the local checkout:

```toml
[tool.uv.sources]
rn-forge-fastapi = { workspace = true }
```

That override is **local development only**. It does not survive into a built
wheel, which is why the `pyproject.toml` still carries the version range.

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-fastapi
```

## Verifying the boundary

```bash
uv run lint-imports
```

The `fastapi-runtime-has-no-tooling` and `web-layers` contracts in
`.importlinter` are what CI trusts: this package imports neither
`rn_forge.django`, `rn_forge.cli` nor `rn_forge.tooling`.
