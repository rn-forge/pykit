# Guides

Run `rn-forge-devops` from inside a uv workspace. Its root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

A workflow keeps only its platform's constructs and calls the command. The usual
flow is:

1. `rn-forge-devops plan [BASE]` selects the packages a change affects and
   writes every job's matrix as `$GITHUB_OUTPUT` lines.
1. The jobs run their checks, each package leaving a marker when it passes.
1. `rn-forge-devops releasable OK_DIR NAME...` prints, in dependency order, the
   packages whose checks all passed and whose prerequisites are releasable.
1. `rn-forge-devops released` prints each package tagged at `HEAD`, for the
   external-install and docs jobs.

```bash
rn-forge-devops plan origin/main >> "$GITHUB_OUTPUT"
```

The other subcommands (`smoke`, `adapters`, `requirements`, `sonar-target`,
`index`, `notes`, `umbrella`) and what a repository declares in
`[tool.workspace-ci]` are in the
[subcommand reference](../reference/subcommands.md).
