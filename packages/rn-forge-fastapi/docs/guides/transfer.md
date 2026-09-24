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
    return await tabular_response(rows, OrderExport, fmt, f"orders.{fmt.extension}")
```

The export model is a pydantic model. Its `serialization_alias`es are the column
headers, and a `computed_field` is a column, which covers foreign-key
traversal, full names and enum display names. Rows are validated with
`from_attributes=True`, so ORM objects work directly. CSV is streamed; xlsx is
written with `rn_forge.commons.data.excel.write_xlsx`. `read_rows` and
`tabular_response` run the tablib work and per-row validation in a worker
thread, so neither blocks the event loop.

Apply the row cap before calling it, and answer an oversize result with
`rn_forge.web.transfer.export_cap_problem`.

## Import

`read_rows` loads an `UploadFile` (csv, tsv or xlsx) and validates each row
against a second pydantic model whose aliases are the external headers. It
never raises for a bad cell:

```python
from rn_forge.fastapi.transfer import problem_response, read_rows
from rn_forge.sqlalchemy import upsert
from rn_forge.web.transfer import import_report_body, row_errors_problem

@app.post("/orders:import")
async def import_orders(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_user),
    validate_only: bool = Query(False, alias="validateOnly"),
):
    result = await read_rows(file, OrderImport)
    # Foreign-key lookups are the application's; append their failures to
    # result.errors as RowError before this check.
    if result.errors:
        return problem_response(row_errors_problem(result.errors, instance="/orders:import"))
    counts = await upsert(
        session, Order, [row.model_dump(by_alias=False) for row in result.valid],
        key=["order_no"], fields=["name", "quantity"], actor=principal.subject,
    )
    if validate_only:
        await session.rollback()
    else:
        await session.commit()
    return import_report_body(
        created=counts.created, updated=counts.updated, skipped=counts.skipped,
        validate_only=validate_only,
    )
```

`upsert` comes from `rn-forge-sqlalchemy`, which this package does not import;
the application joins the two. Any other persistence works the same way.

Any error fails the whole import with a 422 whose `errors[].pointer` is
`/rows/<row>/<column>`. The upsert never commits, so the import is all or nothing in the
request's transaction, and rolling back afterwards is `validateOnly`.

## Conformance

`tests/test_conformance.py` serves `/conformance/orders*` with these helpers and
passes every `transfer.*` case in the shared table.

## Paging a SQLAlchemy list

`order_by_param` and `page_params` parse the request; `rn-forge-sqlalchemy`'s
`keyset` applies them to a `Select` and `next_page_token` writes the next token:

```python
@app.get("/orders")
async def list_orders(
    session: AsyncSession = Depends(get_session),
    params=Depends(page_params(cap=100, default=50)),
    order=Depends(order_by_param(allowed=["orderNo", "createTime"])),
) -> Page[OrderOut]:
    size, cursor = params
    stmt = keyset(
        select(Order),
        columns={"orderNo": Order.order_no, "createTime": Order.create_time},
        terms=order, cursor=cursor, id_column=Order.id,
    )
    rows = (await session.scalars(stmt.limit(size + 1))).all()
    ...
```

The sqlalchemy package's own test suite serves such an application over SQLite and
passes the `pagination.order-by-*` and import cases of the shared conformance
table.
