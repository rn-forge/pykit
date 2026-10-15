# Excel and pandas

The package has one core and one adapter. `rn_forge.data` holds the Excel
helpers, which need only `openpyxl` and `tablib`. `rn_forge.data.pandas` holds
the pandas helpers and imports the core; the core never imports it, so importing
`rn_forge.data` loads no pandas. The `pandas` extra installs pandas for the
adapter, and the facade does not re-export the adapter.

## Workbooks

`ExcelUtils` creates, reads and writes openpyxl workbooks and formats rows.
`CellFormat` carries the formatting to apply and `WorkbookTemplate` describes a
sheet's columns and default formats.

```python
from openpyxl.styles import Font
from rn_forge.data import CellFormat, ExcelUtils

workbook = ExcelUtils.new_workbook()
sheet = workbook.active
sheet.append(["id", "total"])
sheet.append([1001, 42.5])
ExcelUtils.format_row(sheet[2], CellFormat(font=Font(bold=True)))
ExcelUtils.write_workbook(workbook, "build/orders.xlsx")
```

`ExcelUtils.FORMAT_CURRENCY`, `FORMAT_DATE` and `FORMAT_PERCENTAGE` are ready
made formats.

## Exporting a dataset

`write_xlsx` writes a `tablib.Dataset` to `.xlsx` bytes with a number format per
column, which tablib's own xlsx writer does not offer. It streams through a
write-only workbook, so large datasets stay cheap.

```python
from datetime import date

import tablib
from rn_forge.data import write_xlsx

dataset = tablib.Dataset(headers=["name", "due", "total"])
dataset.append(["alice", date(2026, 1, 31), 42.5])
payload = write_xlsx(
    dataset, column_formats={"due": "yyyy-mm-dd", "total": "#,##0.00"}
)
```

A format for a name that is not a header raises `KeyError`.

## pandas

Use the adapter when the code wants pandas for transformation and openpyxl for
workbook-level formatting. `ExcelAdapter` converts between workbooks and
DataFrames, and `PandasUtils` reads typed fields from rows.

```python
from rn_forge.data import ExcelUtils
from rn_forge.data.pandas import ExcelAdapter, PandasUtils

frames = ExcelAdapter.read_dataframe("orders.xlsx")
workbook = ExcelAdapter.from_dataframe(frames)
ExcelUtils.write_workbook(workbook, "build/orders-copy.xlsx")

row = frames["Sheet1"].iloc[0]
customer = PandasUtils.get_string_field(row, "customer_id")
total = PandasUtils.get_decimal_field(row, "total", precision=2)
```

`series_value` and `series_columns` give typed access to a row's value and
labels, and `SeriesRow` is the row type.
