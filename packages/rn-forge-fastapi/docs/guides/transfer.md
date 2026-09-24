# Tabular export and import

`rn_forge.fastapi.transfer` is the wire glue for spreadsheet download and upload.
It needs the `transfer` extra (tablib, openpyxl and `python-multipart`) and is not
imported by `rn_forge.fastapi`. The wire contract is in `rn-forge-web`'s API
conventions; persistence is the application's, through its ORM's own upsert.

## Export

`tabular_format()` is a dependency that negotiates `Accept` or `?format=`. A
`None` result means the client wants the JSON list.

```python
from fastapi import Depends
from rn_forge.fastapi.transfer import tabular_format, tabular_response

@app.get("/orders")
async def list_orders(fmt=Depends(tabular_format(("csv", "xlsx")))):
    rows = await load_orders()
    if fmt is None:
        return {"items": rows}
    return tabular_response(rows, OrderExport, fmt, f"orders.{fmt.extension}")
```

The export model is a pydantic model. Its `serialization_alias`es are the column
headers, and a `computed_field` is a column, which covers foreign-key
traversal, full names and enum display names. Rows are validated with
`from_attributes=True`, so ORM objects work directly. CSV is streamed; xlsx is
written with `rn_forge.commons.data.excel.write_xlsx`.

Apply the row cap before calling it, and answer an oversize result with
`rn_forge.web.transfer.export_cap_problem`.

## Import

`read_rows` loads an `UploadFile` (csv, tsv or xlsx) and validates each row
against a second pydantic model whose aliases are the external headers. It
never raises for a bad cell:

```python
from rn_forge.fastapi.transfer import problem_response, read_rows
from rn_forge.web.transfer import import_report_body, row_errors_problem

@app.post("/orders:import")
async def import_orders(file: UploadFile, validate_only: bool = Query(False, alias="validateOnly")):
    result = await read_rows(file, OrderImport)
    if result.errors:
        return problem_response(row_errors_problem(result.errors, instance="/orders:import"))
    counts = await upsert(result.valid, dry_run=validate_only)
    return import_report_body(**counts, validate_only=validate_only)
```

Any error fails the whole import with a 422 whose `errors[].pointer` is
`/rows/<row>/<column>`. Run the upsert in one transaction and roll it back for
`validateOnly`.

## Conformance

`tests/test_conformance.py` serves `/conformance/orders*` with these helpers and
passes every `transfer.*` case in the shared table.
