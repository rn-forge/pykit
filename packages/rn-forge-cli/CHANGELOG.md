# Changelog

Notable changes to `rn-forge-cli`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Changed

- Malformed `commands` values in a declared CLI surface name the table and key
  in errors, including the index of a non-table entry.

### Fixed

- Restore the console mode after each invocation, including failed and nested
  commands.
- Honor explicit logging level and file options on each invocation, preserving
  existing logging when neither option is passed.

Versioning assessment: patch release; fixes invocation state and clarifies
malformed `commands` errors without changing the public API.

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
