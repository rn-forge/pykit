# Subcommands

Run `rn-forge-devops` from inside a uv workspace. Its root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

| Subcommand | Does |
| -- | -- |
| `plan [BASE]` | Selects the packages a change affects, and writes every job's matrix and package list as `$GITHUB_OUTPUT` lines. |
| `releasable OK_DIR NAME...` | Prints, in dependency order, the selected packages whose checks all passed and whose selected prerequisites are releasable. |
| `released` | Prints `name dir module version` for each `<name>-v<version>` tag at `HEAD`, for `external-install` and `docs`. |
| `smoke PACKAGE [EXTRA]` | Builds the package and its internal requirements as wheels, installs one extra into a clean venv from the wheels' metadata, and imports the configured modules, or the package's own module when it has no smoke table. |
| `adapters` | Checks each package that declares `adapters`: every name has a module or subpackage under the package's source directory and an extra of the same name, and none is repeated. Prints one line per problem to stderr and exits 1 if there are any. |
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
| `[tool.workspace-ci.smoke]` | package | Optional: a package without it is still smoke-tested with no extra, importing its own module. `modules` imported for every smoke run, an optional `setup` script run first, and `extras`: one smoke job per extra with its own modules. |
| `[tool.workspace-ci]` | package | `adapters`: the names of the package's adapter modules. Each must be a module or subpackage of the package and have an extra of the same name; `adapters` checks it. |

## The `plan` outputs

Generated CI workflows read the `plan` outputs. A removed or renamed key, or a
changed row shape, is a breaking change and takes a major version bump. A new
key or a new row field is a minor change.

Each output is one `key=value` line. A string is written as is; a list or a
boolean is written as JSON. "Selected" packages are the packages the change
affects plus every package that depends on one, in release order. "Every" means
every workspace member, whatever the change.

<!-- plan-outputs:start -->

| Key | Value | Scope |
| -- | -- | -- |
| `release-order` | List of package names. | Selected |
| `packages` | List of rows `{name, dir}`. | Selected |
| `postgres` | List of rows `{name, dir, env}`, one per package that declares a PostgreSQL run. `env` is the variable that receives the DSN. | Selected |
| `smoke` | List of rows `{name, extra, marker}`, one per smoke check. `extra` is empty for the run with no extra. `marker` is the file name a passing check leaves for `releasable`. | Selected |
| `suites` | List of rows `{name, args}`, one per `[tool.workspace-ci.suites]` key. `args` is a shell-quoted string. | Every suite |
| `pytest-args` | Shell-quoted string of the root `pytest-args`; empty if none. | Workspace |
| `cov-args` | Shell-quoted string of one `--cov=<module>` per package. | Every |
| `test-paths` | Shell-quoted string of the package directories. | Every |
| `sonar-sources` | Comma-separated `<dir>/src` paths. | Every |
| `sonar-tests` | Comma-separated `<dir>/tests` paths, for packages that have a `tests` directory. | Every |
| `sonar` | `true` if `sonar-project.properties` exists at the root, else `false`. | Workspace |
| `docs` | `true` if `mkdocs.yml` exists at the root, else `false`. | Workspace |

<!-- plan-outputs:end -->

`sonar` and `docs` report only that the file exists; neither is scoped to the
change.

The current kiln workflow no longer reads `sonar-sources`, `sonar-tests`,
`cov-args` and `test-paths`; kiln takes Sonar sources from
`sonar-project.properties`. They are still emitted.
