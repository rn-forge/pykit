# Installation

Base package:

```bash
uv add rn-forge-commons
```

All optional integrations:

```bash
uv add "rn-forge-commons[all]"
```

Targeted extras:

- `coloredlogs` for colored terminal logging
- `excel` for `openpyxl` and `pandas`
- `otel` for OpenTelemetry log correlation
- `pandas` for dataframe helpers
- `testing` for `assertpy` test helpers

Docs commands:

```bash
uv run --directory packages/rn-forge-commons --group docs mkdocs serve
uv run --directory packages/rn-forge-commons --group docs mkdocs build
```
