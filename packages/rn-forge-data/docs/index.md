# rn-forge-data

`rn-forge-data` holds Excel and tabular data helpers, built on
`rn-forge-commons`.

The base install carries `openpyxl` and `tablib[xlsx]` and gives the Excel core,
`rn_forge.data`. The `pandas` extra adds pandas for the adapter,
`rn_forge.data.pandas`, which the core never imports.

## Install

```toml
dependencies = ["rn-forge-data>=0.1,<0.2"]
```

Minimum example: [Excel and pandas](guides/usage.md#workbooks). `write_xlsx`
raises `KeyError` when `column_formats` names a column the dataset lacks, and
the pandas helpers raise `AppException` for a missing required field.

Start with the [guide](guides/index.md), then the
[reference](reference/index.md).
