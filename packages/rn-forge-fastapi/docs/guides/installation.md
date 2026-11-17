# Installation

## Install from PyPI

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-fastapi>=0.4,<0.5"]
```

`rn-forge-web` and `rn-forge-commons` come with it, each as a version range.
FastAPI comes in as an ordinary PyPI dependency, and pydantic and Starlette with
it. The optional `oidc` extra adds JWKS bearer auth and OIDC login; `redis` adds
the Redis stores the auth binding needs outside development
(`rn_forge.auth.redis` and `rn_forge.fastapi.auth.redis`); `transfer` adds
tabular export and import (`rn_forge.fastapi.transfer`); `sse` adds server-sent
events (`rn_forge.fastapi.sse`); `testing` installs `assertpy`, `httpx` and
`pytest`.

## Inside this workspace

The workspace resolves this package to the local checkout, for development only;
see the
[workspace boundaries](https://rn-forge.github.io/pykit/architecture/workspace/)
page. The package imports neither `rn_forge.django`, `rn_forge.cli` nor
`rn_forge.tooling`; `task lint` proves it.
