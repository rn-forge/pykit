# rn-forge-commons

Shared, framework-agnostic utilities for Python programming. Part of the [pykit](../../README.md) workspace.

## Install

```bash
uv add rn-forge-commons
```

Optional extras:

| Extra | Adds |
| --- | --- |
| `coloredlogs` | Colored console log output |
| `excel` | `openpyxl` + `pandas`-backed Excel helpers |
| `pandas` | `pandas`-backed DataFrame/Series helpers |
| `otel` | OpenTelemetry logging instrumentation |
| `testing` | `assertpy` + `pytest` integration helpers |
| `all` | Everything above |

## What's inside

- **`config`** — `Config`: loads JSON/YAML config from a file or directory, deep-merges multiple sources,
  and resolves internal references.
- **`collections`** — `DictUtils`, `ListUtils`, `JsonUtils`, `YamlUtils`: dot-path get/set, deep merge,
  structural comparison, and JSON/YAML (de)serialization.
- **`logging`** — `AppLogger`, `LoggingConfig`: idempotent logging setup via `dictConfig`, built on
  `verboselogs` with a custom `TRACE` level.
- **`dataclasses`** — `DataclassMixin`: adds `as_dict()`, `to_json()`, `to_yaml()`, `from_dict()` to any
  `@dataclass`.
- **`exceptions`** — `AppException`: structured exception base class for the `rn-forge-*` family.
- **`reflection`** — `ReflectUtils`: fully-qualified name resolution, error-message formatting, and
  stack-frame variable inspection.
- **`subprocess`** — `Process`: immutable dataclass that runs a subprocess and captures return code,
  stdout, and stderr.
- **`tasks`** — `Task`, `TaskPool`: parallel task execution via a managed thread pool.
- **`console`** — `CLIArgumentParser`, `BooleanAction`, `KeyValueAction`: `argparse` helpers.
- **`utils`** — `Environment`, `Base64`, `PathUtils`, `AppUtils`: env-var, base64, filesystem, and
  general-purpose value helpers.
- **`excel`** / **`pandas`** — Excel workbook helpers and DataFrame/Series helpers (optional extras).
- **`testing`** — `output_path` fixture and `assertpy` integration, for use from `conftest.py`.

Import from the top-level package for the curated public API:

```python
from rn_forge.commons import AppLogger, Config, DictUtils, JsonUtils

logger = AppLogger.initialize(root_logger_name="my-service")
cfg = Config("config")
logger.info("database.host={}", cfg.get("database.host"))
```

## Docs

Full API reference and guides are built with mkdocs:

```bash
uv run --group docs mkdocs serve   # or `mkdocs build`
```

Source lives in [`docs/`](docs), configured via [`mkdocs.yml`](mkdocs.yml).

## Development

From the repo root or this directory:

```bash
uv run pytest packages/rn-forge-commons
uv run ruff check packages/rn-forge-commons
uv run pyright
```
