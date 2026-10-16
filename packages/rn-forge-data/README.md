# rn-forge-data

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-data/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-data/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-data) ·
[All pykit packages](https://rn-forge.github.io/pykit/)

Excel and tabular data helpers for Python programming, built on
`rn-forge-commons`. The base install carries `openpyxl` and `tablib[xlsx]`; the
`pandas` extra adds the pandas adapter.

- `rn_forge.data` — the core: `ExcelUtils`, `CellFormat`, `WorkbookTemplate` and
  `write_xlsx`. The facade re-exports the core only.
- `rn_forge.data.pandas` — the pandas adapter, behind the `pandas` extra:
  `PandasUtils` and `ExcelAdapter`. The core never imports it; `.importlinter`
  proves that.
