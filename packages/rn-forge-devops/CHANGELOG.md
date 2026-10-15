# Changelog

Notable changes to `rn-forge-devops`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `rn-forge-devops` package: CI and release automation for rn-forge
  repositories in any language, run with uv. It holds the workspace planner
  that was `.github/scripts/workspace_ci.py`, split into a core
  (`rn_forge.devops.ci`), a uv workspace adapter (`rn_forge.devops.uv`), a
  GitHub Actions adapter (`rn_forge.devops.github`) and the `rn-forge-devops`
  console script (`rn_forge.devops.cli`).
