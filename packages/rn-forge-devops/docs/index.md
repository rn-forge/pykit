# rn-forge-devops

`rn-forge-devops` holds the release commands for the pykit workspace. The CI
planner is kiln's `kiln-devops`.

It is built from three modules:

- `rn_forge.devops.requirements`, the `requirements` check: every requirement
  between workspace members is a version range that admits the member's
  current version and has a ceiling.
- `rn_forge.devops.notes`, the `umbrella` subcommand's logic: the umbrella
  release for the newest shipped release page.
- `rn_forge.devops.cli`, the console script that wires the subcommands.

The package depends on `packaging` and no other rn-forge package;
`uv run lint-imports` proves it. The facade re-exports nothing.

Use the [reference](reference/index.md) for the subcommands and the API.
