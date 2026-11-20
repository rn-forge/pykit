# Changelog

Notable changes to `rn-forge-tooling`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- `install` and `upgrade` write `$RNF_HOME/env.sh` and print how to source it
  when `$RNF_HOME/bin` is not on `PATH`; the home contract is a guide page.

### Changed

- The `testing` extra requires `assertpy>=2.36.0`.

## [0.3.3] - 2026-11-17

### Added

- `install --ref` installs a branch, tag or commit of a GitHub repository, and
  `state.json` records `ref` and `commit`.
- `PythonTool` builds a Python tool's runnable command with `uv`, and
  `ToolProduct.preflight` lets a product refuse an install before anything is
  written.

### Changed

- The `rn-forge-commons` requirement admits 0.10 (`<0.11`).
- The `rn-forge-cli` requirement admits 0.2 (`<0.3`).
- `upgrade` follows an install's recorded ref, `status` reports it, and `doctor`
  compares the running version with the recorded package version.

### Fixed

- A failed undo step no longer stops install recovery or hides the initiating
  failure, and a failed restoration no longer deletes the displaced version.

## [0.3.2] - 2026-11-13

### Changed

- The `rn-forge-commons` requirement admits 0.9 (`>=0.8.0,<0.10`).

## [0.3.1] - 2026-10-29

### Changed

- The package declares the MIT licence and is published to PyPI.

## [0.3.0] - 2026-10-25

### Removed

- Breaking: `rn_forge.tooling.generation`, `rn_forge.tooling.state` and
  `rn_forge.tooling.templates`. Import them from
  `rn_forge.commons.generation`, `rn_forge.commons.fs.state` and
  `rn_forge.commons.text.templates` (extra `templates`); the names are
  unchanged. Tooling no longer depends on `jinja2`.

### Changed

- Requires its rn-forge dependencies by version range from pykit's index
  (ADR-0004), not by git URL.

## [0.2.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).
