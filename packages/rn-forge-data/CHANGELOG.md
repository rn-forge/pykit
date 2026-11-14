# Changelog

Notable changes to `rn-forge-data`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Fixed

- `PandasUtils.get_string_field` preserves present `0`, `0.0` and `False` as
  `"0"`, `"0.0"` and `"False"`. Missing values still follow `required`;
  `get_decimal_field` now raises `decimal.InvalidOperation` for a `False`
  cell. Versioning: patch bug fix for `rn-forge-data`; callers relying on
  empty strings for zero/False or decimal zero for False must adjust to these
  corrected results.

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

## [0.1.0] - 2026-10-16

### Added

- The `rn-forge-data` package: Excel and tabular data helpers. The core,
  `rn_forge.data`, holds `ExcelUtils`, `CellFormat`, `WorkbookTemplate` and
  `write_xlsx`, and needs only `openpyxl` and `tablib[xlsx]`. The pandas
  adapter, `rn_forge.data.pandas`, behind the `pandas` extra, holds
  `PandasUtils`, `ExcelAdapter`, `SeriesRow`, `series_value` and
  `series_columns`. These moved from `rn-forge-commons`.
