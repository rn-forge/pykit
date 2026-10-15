# rn-forge-data

`rn-forge-data` holds Excel and tabular data helpers, built on
`rn-forge-commons`.

The base install carries `openpyxl` and `tablib[xlsx]` and gives the Excel core,
`rn_forge.data`. The `pandas` extra adds pandas for the adapter,
`rn_forge.data.pandas`, which the core never imports.

Start with the [guide](guides/index.md), then the
[reference](reference/index.md).
