# Fixtures

`FixtureManager` (requires the `fixtures` extra) converts Excel workbooks into Django JSON
fixtures and can load them with `loaddata`.

```python
from pathlib import Path

from rn_forge.django.fixtures import (
    ColumnType,
    FixtureColumn,
    FixtureDefinition,
    FixtureManager,
    FixtureManagerConfig,
)

config = FixtureManagerConfig(
    root_path=Path("fixtures"),
    settings_module="myproject.settings",
    fixtures=[
        FixtureDefinition(
            app_label="orders",
            model="product",
            input_file="products.xlsx",
            output_file="products.json",
            columns=[
                FixtureColumn(name="sku"),
                FixtureColumn(name="price", type=ColumnType.DECIMAL),
                FixtureColumn(name="active", type=ColumnType.BOOLEAN),
                FixtureColumn(name="category", type=ColumnType.FOREIGN_KEY),
                FixtureColumn(name="tags", type=ColumnType.MANY_TO_MANY, required=False),
            ],
            key_columns=["sku"],
        ),
    ],
)

FixtureManager(config).prepare_fixtures().load_data()
```

Each `FixtureDefinition` reads one worksheet (named after `model`) from
`root_path/input/<app_label>/<input_file>` and writes Django `loaddata`-ready JSON to
`root_path/output/<app_label>/<output_file>`.

- `ColumnType.MANY_TO_MANY` columns are read from a separate worksheet named after the column,
  joined back to the main sheet via `key_columns`.
- `common_fields` on a `FixtureDefinition` are merged into every generated row (e.g. a constant
  `tenant_id`).
- `load_data(fixture_models=["orders.product"])` loads a subset; omit it (or pass `["ALL"]`) to
  load everything configured. It bootstraps Django (`DJANGO_SETTINGS_MODULE` +
  `django.setup()`) if not already configured, using `settings_module`.
