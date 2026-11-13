# Guides

Run `rn-forge-devops requirements` from inside a uv workspace. Its root is the
nearest directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`. `umbrella` needs no workspace.

```bash
rn-forge-devops requirements
git ls-remote --tags --refs origin | rn-forge-devops umbrella docs/releases release-body.md --site-url https://rn-forge.github.io/pykit/
```

The subcommands are in the [subcommand reference](../reference/subcommands.md).
