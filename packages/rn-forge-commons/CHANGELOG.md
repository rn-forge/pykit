# Changelog

Notable changes to `rn-forge-commons`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Removed

- Breaking: `rn_forge.commons.data.excel` and `rn_forge.commons.data.pandas`,
  and the pandas aliases `SeriesRow`, `series_value` and `series_columns` in
  `rn_forge.commons.lang.types`. They moved to `rn-forge-data`, with the same
  class names; import them from `rn_forge.data` and `rn_forge.data.pandas`.
- Breaking: the `excel` and `pandas` extras. Depend on `rn-forge-data`, or
  `rn-forge-data[pandas]`, instead.

## [0.5.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).

`rn-forge-commons-v0.1.0` to `rn-forge-commons-v0.2.2` predate this file; their
notes are on the [GitHub Releases](https://github.com/rn-forge/pykit/releases)
page.
