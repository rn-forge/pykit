# Installation

## Releases are pinned git tags, not PyPI versions

None of the `rn-forge-*` packages is published to PyPI. A release is a **git
tag** on this repository, and every consumer declares it as a pinned direct
URL:

```toml
[project]
dependencies = [
  "rn-forge-web @ git+https://github.com/rn-forge/pykit@rn-forge-web-v0.1.0#subdirectory=packages/rn-forge-web",
]
```

`uv add rn-forge-web` will not work: there is nothing on the index under that
name. Pin the tag explicitly rather than tracking a branch — an unpinned
`git+…` reference re-resolves on every lock refresh, which is how a library
upgrade arrives without anyone deciding it should.

`rn-forge-commons` comes in transitively, itself pinned to the tag this release
was built against. There is nothing else to install: this package has no
third-party dependency of its own, and no optional extras.

## Inside this workspace

`packages/rn-forge-web` is a `uv` workspace member, so the root
`[tool.uv.sources]` overrides the URL above with the local checkout:

```toml
[tool.uv.sources]
rn-forge-web = { workspace = true }
```

That override is **local development only**. It does not survive into a built
wheel, which is why the `pyproject.toml` still carries the full URL — that is
what a consumer outside the workspace actually resolves.

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
what CI trusts, because they see transitive imports. A grep over the source is
a useful fast local check but is not the gate.
