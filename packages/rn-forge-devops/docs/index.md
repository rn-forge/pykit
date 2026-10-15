# rn-forge-devops

`rn-forge-devops` is CI and release automation for rn-forge repositories in any
language, run with uv.

The `rn-forge-devops` command reads a repository's workspace manifests, selects
the packages a change affects, prints every CI job's matrix, and gates each
package's release on its checks. A workflow file keeps only its platform's
constructs and calls the command.

It is built from four modules:

- `rn_forge.devops.ci`, the core: the member graph, change selection, check
  matrices and release gating. It knows neither the CI platform nor the stack.
- `rn_forge.devops.uv`, the uv workspace adapter: it reads the
  `[tool.uv.workspace]` members, their internal requirements and their
  `[tool.workspace-ci]` tables into the core's graph, and runs `smoke`.
- `rn_forge.devops.github`, the GitHub Actions adapter: it writes
  `$GITHUB_OUTPUT` lines and reads the event context.
- `rn_forge.devops.cli`, the console script that wires the subcommands to the
  core and the adapters.

The package depends on `packaging` and no other rn-forge package. The core
imports neither adapter; `uv run lint-imports` proves both rules. The facade
re-exports the core only.

Use the [reference](reference/index.md) for the subcommands and the API.
