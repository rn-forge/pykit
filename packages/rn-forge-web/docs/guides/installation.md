# Installation

## Install from PyPI

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-web>=0.3,<0.4"]
```

`rn-forge-commons` comes in transitively, as a version range. There is nothing
else to install: this package has no third-party dependency of its own, and no
optional extras.

## Inside this workspace

`packages/rn-forge-web` is a `uv` workspace member, so the root
`[tool.uv.sources]` overrides the requirement above with the local checkout:

```toml
[tool.uv.sources]
rn-forge-web = { workspace = true }
```

That override is **local development only**. It does not survive into a built
wheel, which is why the `pyproject.toml` still carries the version range — that
is what a consumer outside the workspace actually resolves.

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-web
```

## Verifying the boundary

The package's central claim is that it imports no web framework and neither of
the development-layer packages. That claim is executable:

```bash
uv run lint-imports
```

The `web-is-framework-free` and `web-layers` contracts in `.importlinter` are
what CI trusts, because they see transitive imports. A grep over the source is a
useful fast local check but is not the gate.
