# Changelog

Notable changes to `rn-forge-cli`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

## [0.2.2] - 2026-11-22

### Added

- `CliApp(version=...)` adds an eager `--version` that prints
  `<name> <version>`.
- The `[cli]` table's `distribution` key supplies that version from the
  installed distribution.

### Changed

- Requires `typer>=0.29.1`.

## [0.2.1] - 2026-11-20

### Changed

- The `testing` extra requires `assertpy>=2.36.0`.

## [0.2.0] - 2026-11-17

### Changed

- The `rn-forge-commons` requirement admits 0.10 (`<0.11`).
- A declared command's default `--help` ends before the first docstring section
  (`Args:`, `Returns:`, `Raises:` and the like).
- Malformed `commands` values in a declared CLI surface name the table and key
  in errors, including the index of a non-table entry.
- A `[cli]` table with a key that names no field fails to load.

### Fixed

- Square brackets that are not Rich markup, such as `[kiln]`, show in a declared
  command's `--help` instead of being dropped.
- Restore the console mode after each invocation, including failed and nested
  commands.
- Honor explicit logging level and file options on each invocation, preserving
  existing logging when neither option is passed.

## [0.1.3] - 2026-11-13

### Changed

- The `rn-forge-commons` requirement admits 0.9 (`>=0.8.0,<0.10`).

## [0.1.2] - 2026-10-29

### Changed

- The package declares the MIT licence and is published to PyPI.

## [0.1.1] - 2026-10-25

### Changed

- Requires its rn-forge dependencies by version range from pykit's index
  (ADR-0004), not by git URL.

## [0.1.0] - 2026-09-27

First release.
