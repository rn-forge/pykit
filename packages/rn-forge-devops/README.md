# rn-forge-devops

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-devops/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-devops/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-devops)
· [All pykit packages](https://rn-forge.github.io/pykit/)

Release commands for the pykit workspace. The CI planner is kiln's
`kiln-devops`; this package keeps only the commands pykit's own release process
calls.

It depends on `packaging` and on no other rn-forge package. It is a CI tool, not
a library an application depends on.

- `rn_forge.devops.requirements` — the `requirements` check: every requirement
  between workspace members is a version range that admits the member's
  current version and has a ceiling.
- `rn_forge.devops.notes` — the `umbrella` subcommand: the umbrella release for
  the newest shipped release page.
- `rn_forge.devops.cli` — the `rn-forge-devops` console script.

The package facade re-exports nothing. The package never imports another
`rn_forge` package, and `.requirements` and `.notes` never import each other;
`.importlinter` proves both.

## Usage

Run `requirements` from inside a uv workspace; the workspace root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

```bash
uvx --from "rn-forge-devops>=0.4,<0.5" rn-forge-devops requirements
```

The subcommands are described in the
[subcommand reference](https://rn-forge.github.io/pykit/packages/rn-forge-devops/latest/reference/subcommands.html).
