# rn-forge-commons

Shared, framework-agnostic utilities for Python programming. Part of the [pykit](../../README.md) workspace.

## Install

```bash
uv add rn-forge-commons
```

Optional extras:

| Extra | Adds |
| --- | --- |
| `json` | JSON-formatted log output (`python-json-logger`) |
| `excel` | `openpyxl` + `pandas`-backed Excel helpers |
| `pandas` | `pandas`-backed DataFrame/Series helpers |
| `otel` | OpenTelemetry logging instrumentation |
| `testing` | `assertpy` + `pytest` integration helpers |
| `resilience` | Async circuit breakers and HTTP retries (`purgatory`, `stamina`, `httpx`) |
| `structlog` | Structured logging over the existing stdlib handlers |
| `all` | Everything above |

Console log output is Rich-formatted by default (a hard dependency) when stdout is a TTY.

## What's inside

- **`config`** — `Config`: loads JSON/YAML config from a file or directory, deep-merges multiple sources,
  and resolves internal references.
- **`collections`** — `DictUtils`, `ListUtils`: dot-path get/set, deep merge, structural comparison,
  sorting, filtering, and grouping.
- **`documents`** — `JsonUtils`, `YamlUtils`, `DocumentUtils`, `ConfigFormat`: JSON/YAML/TOML
  (de)serialization and file I/O, plus comment-preserving round-trip editing of config documents.
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
- **`blocks`** — `ManagedBlock`: render, extract and remove a generator-owned fenced block inside a
  file somebody else owns (`.gitignore`, `CLAUDE.md`, `mkdocs.yml`).
- **`findings`** — `Finding`, `Severity`: the structured result shape every checker and doctor
  reports in, serialisable for `--json`.
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

### Moved to `rn-forge-tooling`

The developer-tooling surface now lives in
[`rn-forge-tooling`](../rn-forge-tooling/README.md), which depends on this package. There are no
compatibility re-exports — that would reverse the dependency:

| Was | Now |
| --- | --- |
| `rn_forge.commons.console` | `rn_forge.tooling.console` |
| `rn_forge.commons.cli` | `rn_forge.tooling.cli` |
| `rn_forge.commons.state` | `rn_forge.tooling.state` |
| `rn_forge.commons.templates` (`templates` extra) | `rn_forge.tooling.templates` |
| `DirectoryLock`, `PathUtils.atomic_symlink`, `PathUtils.extract_archive` | `rn_forge.tooling.install` |

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
