# Developing pykit

The workspace's local setup and validation commands. Run them from the
repository root unless a command says otherwise.

## Setup

The repository is a uv workspace with ten packages. Install every package with
its `dev` and `docs` dependency groups, which bring each package's optional
extras, with:

```bash
task setup
```

Package code targets Python 3.14 or later, and the floor stays at `>=3.14`
across the workspace; lowering it would be a workspace decision, not a package
one. Use a patch release: on a 3.14 release candidate, `mkdocstrings`' pydantic
support fails
(`_eval_type() got an unexpected keyword argument 'prefer_fwd_module'`) and
every docs build exits 1. Python 3.14.2 and later build cleanly.

## Commands

Every gate is a `task` verb, run from the repository root.

| Check | Command |
| -- | -- |
| Install | `task setup` |
| All tests | `task test` |
| Lint: ruff, format check, import boundaries, Markdown and TOML formatting, dependency audit, licences | `task lint` |
| Format in place | `task format` |
| Strict type check | `task typecheck` |
| Combined documentation, root and every package, strict | `task docs:build` |
| Lint, type check, tests and documentation together | `task validate` |
| Regenerate the derived documentation regions | `task docs:generate` |
| Broker profile (`rn-forge-auth`, needs Docker) | `task ci:integration -- rn-forge-auth` |

A narrower run filters a run through `task test` and is not a gate:
`task validate` is the gate.

| Run | Command |
| -- | -- |
| One package's tests | `task test PACKAGE_DIRS=packages/rn-forge-cli` |
| One test file or test, by package-relative id | `PYTEST_ADDOPTS='tests/test_command_paths.py::test_exit_codes' task test PACKAGE_DIRS=packages/rn-forge-cli` |
| By keyword | `PYTEST_ADDOPTS='-k test_name' task test PACKAGE_DIRS=packages/<pkg>` |
| Fast isolated tests (`rn-forge-django`, `rn-forge-web`) | `PYTEST_ADDOPTS='-m unit' task test PACKAGE_DIRS=packages/<pkg>` |
| Database-backed tests (`rn-forge-django`, `rn-forge-sqlalchemy`) | `task ci:integration -- <package>` (needs Docker) |

The broker profile tests run against a Keycloak container and skip without
`RN_FORGE_AUTH_KEYCLOAK_URL`. CI runs them in the `integration` job of `ci.yml`,
against the `keycloak` service that `rn-forge-auth` declares in
`[tool.workspace-ci.integration.keycloak]`. The broker profile (`rn-forge-auth`,
needs Docker) runs as `task ci:integration -- rn-forge-auth`.

## Dependency audit

`task lint` fails on a known vulnerability in `uv.lock` (`pip-audit` over
`uv export --frozen`, [ADR-0015](../adr/ADR-0015.md)), and CI runs it in the
`validate` job. To accept a finding, add its advisory ID and the reason to the
`ignore` list of `[ci.checks.pip-audit]` in `.rn-forge/kiln/config.toml`, as
`ignore = [{ id = "<ID>", reason = "<why, and when to revisit>" }]`, then run
`task kiln:apply`. An entry without a reason is not allowed.

`task lint` also fails on a dependency whose licence matches GPL, AGPL or
`UNKNOWN`, and allows LGPL. Workspace members are left out, so the check covers
third-party dependencies only. `[ci.checks.licenses]` in the same file sets
`deny` and `ignore`; a dual-licensed package used under its permissive option
goes in `ignore`, then `task kiln:apply`.

`task lint` also runs ruff's `S` rules (Bandit's checks, including the Django
ones) over the packages, and CI scans the full git history for secrets with
gitleaks (`task ci:secret-scan`), which is not part of `task lint`. Report a
vulnerability privately through GitHub private vulnerability reporting, as
`SECURITY.md` says.

## Sonar feedback

Connect SonarQube for IDE to the project's SonarCloud server (connected mode)
for instant rule feedback while editing. Taint analysis and the quality gate
need a server analysis, which the IDE cannot certify.

To analyze the working tree before pushing:

```bash
task sonar:local -- --dry-run
task sonar:local
```

The first command prints the target branch and the exact test and scanner
commands; it needs no token and runs nothing. The second runs the workspace
coverage tests, then uploads the code and results to SonarCloud and exits with
the quality gate's status. A full scan needs:

- network access, and a non-`main` branch on a plan with branch analysis; the
  verb refuses `main`, and `--branch` must match the checked-out branch unless
  HEAD is detached;
- a SonarCloud token provided by the project owner, exported as `SONAR_TOKEN`;
- the official
  [SonarScanner CLI](https://docs.sonarsource.com/sonarqube-cloud/advanced-setup/ci-based-analysis/sonarscanner-cli/)
  on `PATH`. The repository adds no dependency for it.

A scan of uncommitted changes is not CI evidence for a commit.

## Dependabot pull requests

Bring a Dependabot pull request up to date with `@dependabot rebase` or GitHub's
"Update with rebase". Do not use "Update branch": it merges `main` into the
branch and puts a merge commit on `main`, which breaks its linear history.

## Scorecard

`.github/workflows/scorecard.yml` runs OpenSSF Scorecard on pushes to `main`,
weekly and on demand. It reports only: the SARIF result goes to code scanning
and is kept as the `scorecard-sarif` artifact, and no score fails a build.

## Documentation builds

Each package also has a standalone MkDocs site. `task docs:build` builds the
root site and then every package's own site, each with `--strict`: the root site
includes all ten, but a combined build does not show that each standalone site
resolves its own links, so the task checks both. `task docs:build -- <dir>`
writes the root site to `<dir>`, which keeps an existing preview.

## Tests and types

Tests live under each package's `tests/` tree. The root pytest configuration
uses `importlib` import mode and registers the `unit`, `integration` and
`postgres` markers. Source under `packages/` is checked by Pyright in strict
mode; tests and two framework-specific web documentation examples are excluded,
while the framework-neutral ASGI example is checked.

For a new package, follow [Adding a package](../runbooks/adding-a-package.md).
The [workspace boundaries](../architecture/workspace.md) describe the import
contracts it must respect.
