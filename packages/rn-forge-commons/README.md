# rn-forge-commons

Shared, framework-agnostic utilities for Python programming. Part of the [pykit](../../README.md) workspace.

## Install

Not published to PyPI: a release is a git tag, and a consumer pins one by
direct URL.

```toml
[project]
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
]
```

Optional extras:

| Extra | Adds |
| --- | --- |
| `auth` | JWT/JWKS token verification and OIDC discovery (`pyjwt[crypto]`) |
| `json` | JSON-formatted log output (`python-json-logger`) |
| `excel` | `openpyxl` + `pandas`-backed Excel helpers |
| `pandas` | `pandas`-backed DataFrame/Series helpers |
| `pydantic` | Strict pydantic models for configuration documents, with every failure named by dotted path |
| `otel` | OpenTelemetry logging instrumentation |
| `testing` | `assertpy` + `pytest` integration helpers |
| `resilience` | Async circuit breakers and HTTP retries (`purgatory`, `stamina`, `httpx`) |
| `structlog` | Structured logging over the existing stdlib handlers |
| `all` | Everything above |

Console log output is Rich-formatted by default (a hard dependency) when stdout is a TTY.

## What's inside

Modules are grouped by kind of mechanism. Public class names do not encode the
grouping and are all re-exported from the package facade, so
`from rn_forge.commons import PathUtils` works regardless of which submodule
holds it.

**Top level**

- **`config`** — `Config`: loads JSON/YAML config from a file or directory, deep-merges multiple
  sources, and resolves internal references.
- **`exceptions`** — `AppException`: structured exception base class for the `rn-forge-*` family.
- **`findings`** — `Finding`, `Severity`: the structured result shape every checker and doctor
  reports in, serialisable for `--json`.
- **`testing`** — `output_path` fixture and `assertpy` integration, for use from `conftest.py`.

**`lang/`** — Python objects themselves; no filesystem, no outside world.

- **`collections`** — `DictUtils`, `ListUtils`: dot-path get/set, typed dot-path reads that treat
  a wrong-shaped value as absent (`get_mapping`, `get_list`, `get_strings`, `get_str`,
  `get_bool`), layered merge with provenance, flatten, structural comparison, sorting, filtering, grouping.
- **`dataclasses`** — `DataclassMixin`: adds `as_dict()`, `to_json()`, `to_yaml()`, `from_dict()`
  to any `@dataclass`, reconstructing nested dataclasses and enum members on the way back.
  `from_dict()` is **strict**: a value whose type does not match its field is rejected as an
  `AppException` naming the offending field. `LenientDataclassMixin`: the same surface with type
  checking off — for a record whose input is known-ragged, and for the two annotations dacite
  cannot see through (a PEP 695 `type` alias, an unbound type variable), which the module
  docstring spells out. `StrictDataclassMixin`: type checking plus rejection of unknown keys at
  every nesting level, named by dotted path (`repository.archtype`) — for configuration documents.
- **`models`** (`pydantic` extra) — `StrictModel`, `parse_model`, `ModelValidationError`: pydantic
  models that are strict, frozen and reject unknown keys, raising one `AppException` that names
  every failing key by its dotted path. Not on the facade, so `import rn_forge.commons` never loads
  pydantic.
- **`reflection`** — `ReflectUtils`: fully-qualified name resolution, error-message formatting,
  and stack-frame variable inspection.
- **`types`** — the recursive `JsonValue` alias.
- **`utils`** — `AppUtils`, `Base64`: bool parsing, emptiness checks, dynamic imports, null-safe
  attribute access, string joining, unified diffs, and base64 encode/decode.

**`fs/`** — everything that reads or writes a real file.

- **`paths`** — `PathUtils`: atomic writes, backups, temp dirs, repository-root discovery and the
  `assert_within` path-escape guard.
- **`hashing`** — `ContentHash`: content and file digests, for detecting drift.
- **`locks`** — `DirectoryLock`, `atomic_symlink`: cross-process serialization and atomic
  publication.
- **`blocks`** — `ManagedBlock`: render, extract and remove a generator-owned fenced block inside a
  file somebody else owns (`.gitignore`, `CLAUDE.md`, `mkdocs.yml`), preserving every byte outside
  the markers.
- **`documents`** — `JsonUtils`, `YamlUtils`, `DocumentUtils`, `ConfigFormat`: JSON/YAML/TOML
  (de)serialization and file I/O, plus comment-preserving round-trip editing of config documents.

**`data/`** (optional extras) — `excel`, `pandas`: Excel workbook helpers and DataFrame/Series
helpers.

**`logging/`**

- **`logging`** — `AppLogger`, `LoggingConfig`: idempotent logging setup via `dictConfig`, built on
  `verboselogs` with a custom `TRACE` level. Console records go to **stderr**, so a command's
  stdout carries only its result.
- **`structlog`** (`structlog` extra) — `StructLogger`: structured logging over the same handlers.

**`runtime/`** — the process and its surroundings.

- **`environment`** — `Environment`: typed env-var access, plus the `require`/`forbid` fail-fast
  guards a process calls at startup.
- **`console`** — `AppConsole`, `OutputMode`, `console`: a Rich output facade with RICH/PLAIN/
  QUIET/JSON modes, semantic helpers, a one-call table builder and confirm/prompt/status
  interaction. Imports no Typer or Click, so a script, a worker or a Django management command
  uses it directly; `rn-forge-cli` drives its mode from `--quiet`/`--json`.
- **`subprocess`** — `Process`: immutable dataclass that runs a subprocess and captures return
  code, stdout, and stderr.
- **`tasks`** — `Task`, `TaskPool`: parallel task execution via a managed thread pool.
- **`plugins`** — `EntryPointLoader`: failure-isolated entry-point plugin discovery.

**`integration/`** — protocols for the systems an application talks to.

- **`messaging`**, **`objects`**, **`secrets`** — `MessageBus`, `ObjectStore`, `SecretStore` and
  their in-memory implementations.
- **`resilience`** (`resilience` extra) — async circuit breakers and a retrying HTTP client.
- **`auth`** (`auth` extra) — `JwtVerifier`, `JwksCache` and `discover_oidc`: bearer-token
  verification returning verified claims. The `Principal` and the 401 wire shape are `rn-forge-web`'s.

Import from the top-level package for the curated public API:

```python
from rn_forge.commons import AppLogger, Config, DictUtils, JsonUtils

logger = AppLogger.initialize(root_logger_name="my-service")
cfg = Config("config")
logger.info("database.host={}", cfg.get("database.host"))
```

### The developer-tooling packages

The command-line layer lives in [`rn-forge-cli`](../rn-forge-cli/README.md) and the file-owning
tooling in [`rn-forge-tooling`](../rn-forge-tooling/README.md). Both depend on this package;
neither is depended on by it, and there are deliberately no compatibility re-exports in either
direction — that would reverse the dependency. `uv run lint-imports` proves it.

| Concern | Package |
| --- | --- |
| `AppConsole`, Typer app factory, standard options, exit codes, the `[cli]` surface | `rn-forge-cli` |
| `StateStore`, `TemplateEngine`, the generation engine, `extract_archive`, docs checkers | `rn-forge-tooling` |

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
