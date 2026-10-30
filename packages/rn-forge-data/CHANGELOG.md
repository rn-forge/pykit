# Changelog

Notable changes to `rn-forge-data`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

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
