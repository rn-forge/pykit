# rn-forge-data

`rn-forge-data` holds Excel and tabular data helpers, built on
`rn-forge-commons`.

The base install carries `openpyxl` and `tablib[xlsx]`. The `pandas` extra adds
pandas for the `rn_forge.data.pandas` adapter, which the core never imports.

Use the [reference](reference/index.md) for the API.

## Excel and pandas

```python
from rn_forge.data import ExcelUtils
from rn_forge.data.pandas import ExcelAdapter

frames = ExcelAdapter.read_dataframe("orders.xlsx")
workbook = ExcelAdapter.from_dataframe(frames)
ExcelUtils.write_workbook(workbook, "build/orders-copy.xlsx")
```

`ExcelAdapter` needs the `pandas` extra.

`write_xlsx` writes a `tablib.Dataset` to `.xlsx` bytes with per-column number
formats, which tablib's own xlsx writer does not offer:

```python
import tablib
from rn_forge.data import write_xlsx

dataset = tablib.Dataset(headers=["name", "due", "total"])
dataset.append(["alice", date(2026, 1, 31), 42.5])
payload = write_xlsx(dataset, column_formats={"due": "yyyy-mm-dd", "total": "#,##0.00"})
```
