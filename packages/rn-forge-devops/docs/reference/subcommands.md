# Subcommands

Run `rn-forge-devops` from inside a uv workspace. Its root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

| Subcommand | Does |
| -- | -- |
| `plan [BASE]` | Selects the packages a change affects, and writes every job's matrix and package list as `$GITHUB_OUTPUT` lines. |
| `releasable OK_DIR NAME...` | Prints, in dependency order, the selected packages whose checks all passed and whose selected prerequisites are releasable. |
| `released` | Prints `name dir module version` for each `<name>-v<version>` tag at `HEAD`, for `external-install` and `docs`. |
| `smoke PACKAGE [EXTRA]` | Builds the package and its internal requirements as wheels, installs one extra into a clean venv from the wheels' metadata, and imports the configured modules. |
| `sonar-target` | Prints the `branch-arg=` line for the Sonar scan, from the `EVENT_NAME`, `REF_TYPE` and `REF_NAME` environment variables. |

## What it discovers

- **Packages:** the members of the root `[tool.uv.workspace]`, including
  `exclude`. No name prefix is assumed.
- **Internal requirements:** workspace members named in a package's
  dependencies, optional dependencies and dependency groups.
- **Import name:** `[tool.uv.build-backend].module-name`, used for `--cov`, the
  external-install import and the smoke imports.
- **Optional jobs:** `sonar` runs only if `sonar-project.properties` exists;
  `docs` only if `mkdocs.yml` exists.

An empty, invalid or non-ancestor `BASE` selects every package. A change under
`docs/` selects no package; any other change outside the members selects every
package.

## What a repository declares

| Table | Where | Holds |
| -- | -- | -- |
| `[tool.workspace-ci]` | root | `pytest-args` for package test runs. |
| `[tool.workspace-ci.suites]` | root | A named workspace-wide pytest run per key, each its own job. |
| `[tool.workspace-ci.postgres]` | package | `env`: the variable that receives a PostgreSQL DSN; the package's tests run again against a service container. |
| `[tool.workspace-ci.smoke]` | package | `modules` imported for every smoke run, an optional `setup` script run first, and `extras`: one smoke job per extra with its own modules. |
