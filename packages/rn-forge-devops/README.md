# rn-forge-devops

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-devops/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-devops/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-devops)
· [All pykit packages](https://rn-forge.github.io/pykit/)

CI and release automation for rn-forge repositories in any language, run with
uv. The `rn-forge-devops` command reads a repository's workspace manifests,
selects the packages a change affects, prints every CI job's matrix, and gates
each package's release on its checks. Workflow files call it instead of carrying
that logic.

It depends on `packaging` and on no other rn-forge package. It is a CI tool, not
a library an application depends on.

- `rn_forge.devops.ci` — the core: the member graph, change selection, check
  matrices and release gating. It knows neither the CI platform nor the stack.
- `rn_forge.devops.requirements` — the `requirements` check: every requirement
  between workspace members is a version range that admits the member's current
  version and has a ceiling.
- `rn_forge.devops.uv` — the uv workspace adapter: it reads
  `[tool.uv.workspace]` members, their internal requirements and their
  `[tool.workspace-ci]` tables, and runs `smoke`.
- `rn_forge.devops.github` — the GitHub Actions adapter: `$GITHUB_OUTPUT` lines
  and the event context.
- `rn_forge.devops.index` and `rn_forge.devops.releases` — the `index`
  subcommand: a PEP 503 simple index rendered from a repository's GitHub
  Release files, and the adapter that reads them with `gh`.
- `rn_forge.devops.cli` — the `rn-forge-devops` console script.

The package facade re-exports the planner core only. The core never imports an
adapter, and the package never imports another `rn_forge` package;
`.importlinter` proves both.

## Usage

Run it from inside a uv workspace; the workspace root is the nearest directory
at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

```bash
uvx --from "rn-forge-devops @ git+https://github.com/rn-forge/pykit@rn-forge-devops-v0.1.0#subdirectory=packages/rn-forge-devops" \
  rn-forge-devops plan
```

The subcommands and the `[tool.workspace-ci]` tables are described in the
[subcommand reference](https://rn-forge.github.io/pykit/packages/rn-forge-devops/latest/reference/subcommands.html).
