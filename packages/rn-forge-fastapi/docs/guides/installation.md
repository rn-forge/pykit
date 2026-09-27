# Installation

## Releases are pinned git tags, not PyPI versions

None of the `rn-forge-*` packages is published to PyPI. A release is a **git
tag** on this repository, and every consumer declares it as a pinned direct
URL:

```toml
[project]
dependencies = [
  "rn-forge-fastapi @ git+https://github.com/rn-forge/pykit@rn-forge-fastapi-v0.1.0#subdirectory=packages/rn-forge-fastapi",
]
```

`uv add rn-forge-fastapi` will not work: there is nothing on the index under
that name. Pin the tag explicitly rather than tracking a branch — an unpinned
`git+…` reference re-resolves on every lock refresh, which is how a library
upgrade arrives without anyone deciding it should.

`rn-forge-web` and `rn-forge-commons` come in transitively, each pinned to the
tag this release was built against. FastAPI comes in as an ordinary PyPI
dependency, and pydantic and Starlette with it. The optional `oidc` extra adds JWKS bearer auth; `transfer` adds tabular
export and import (`rn_forge.fastapi.transfer`).

## Inside this workspace

`packages/rn-forge-fastapi` is a `uv` workspace member, so the root
`[tool.uv.sources]` overrides the URL above with the local checkout:

```toml
[tool.uv.sources]
rn-forge-fastapi = { workspace = true }
```

That override is **local development only**. It does not survive into a built
wheel, which is why the `pyproject.toml` still carries the full URL.

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
