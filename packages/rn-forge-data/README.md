# rn-forge-data

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-data/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-data/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-data) ·
[All pykit packages](https://rn-forge.github.io/pykit/)

Excel and tabular data helpers for Python programming, built on
`rn-forge-commons`. The base install carries `openpyxl` and `tablib[xlsx]`; the
`pandas` extra adds the pandas adapter.

## Install

```toml
dependencies = ["rn-forge-data>=0.1,<0.2"]
```

The `pandas` extra adds `pandas` for `rn_forge.data.pandas`.

## Minimum example

```python
from rn_forge.data import ExcelUtils

workbook = ExcelUtils.new_workbook()
sheet = workbook.active
sheet.append(["id", "total"])
sheet.append([1001, 42.5])
ExcelUtils.write_workbook(workbook, "build/orders.xlsx")
```

## Errors

`write_xlsx` raises `KeyError` when `column_formats` names a column the dataset
lacks. The pandas helpers raise `AppException` for a missing required field.

- `rn_forge.data` — the core: `ExcelUtils`, `CellFormat`, `WorkbookTemplate` and
  `write_xlsx`. The facade re-exports the core only.
- `rn_forge.data.pandas` — the pandas adapter, behind the `pandas` extra:
  `PandasUtils` and `ExcelAdapter`. The core never imports it; `.importlinter`
  proves that.
