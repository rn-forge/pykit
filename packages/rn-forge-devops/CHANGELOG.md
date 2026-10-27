# Changelog

Notable changes to `rn-forge-devops`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- `[tool.workspace-ci.redis]`: a package's tests run again against a Redis
  service, with the URL in the variable `env` names. The `plan` output gains
  `redis`, and the check marker is `<package>.redis`.

## [0.3.0] - 2026-10-25

### Added

- The `index` subcommand: `rn-forge-devops index --repo OWNER/NAME --out DIR`
  writes a PEP 503 simple index of the repository's published `rn-forge-*`
  release files.
- The `requirements` subcommand: it fails when a workspace member's requirement
  on another member is a URL, excludes that member's current version or has no
  upper bound.

## [0.2.0] - 2026-10-18

### Changed

- A package with no `[tool.workspace-ci.smoke]` table is still smoke-tested:
  `plan` lists its empty-extra smoke entry, `releasable` requires its
  `<name>.smoke` marker, and `smoke` imports the package's own module.

## [0.1.0] - 2026-10-16

### Added

- The `rn-forge-devops` package: CI and release automation for rn-forge
  repositories in any language, run with uv. It holds the workspace planner
  that was `.github/scripts/workspace_ci.py`, split into a core
  (`rn_forge.devops.ci`), a uv workspace adapter (`rn_forge.devops.uv`), a
  GitHub Actions adapter (`rn_forge.devops.github`) and the `rn-forge-devops`
  console script (`rn_forge.devops.cli`).
- The `adapters` subcommand and the `adapters` key of `[tool.workspace-ci]`: a
  package lists its adapter names, and the command fails when a name has no
  module or no extra of the same name, or is repeated.
