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

The package depends on `packaging` and no other rn-forge package; `task lint`
proves it. The facade re-exports nothing.

Run it with
`uvx --from "rn-forge-devops>=0.4,<0.5" rn-forge-devops requirements`; the
package has no extras. Examples: [Guides](guides/index.md). Exit codes: 0 no
problem, 1 an incompatible requirement, 2 invalid input
([contract](reference/subcommands.md)).

Use the [reference](reference/index.md) for the subcommands and the API.
