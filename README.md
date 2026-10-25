# pykit

Development kit for Python programming. A
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| -- | -- | -- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | Runtime-neutral utilities, grouped by kind of mechanism: `lang` (collections, dataclasses, reflection, values), `fs` (paths, hashing, locks, blocks, documents), `data` (Excel/pandas), `text` (templates — behind an extra), `logging`, `runtime` (environment, subprocess, tasks, plugins) and `integration` (messaging/object/secret protocols, resilience), plus config, exceptions, findings and testing helpers. No web framework. |
| [`rn-forge-cli`](packages/rn-forge-cli) | `rn_forge.cli` | The shared command-line layer: `CliApp` (a `typer.Typer` subclass), the standard option set, the error-to-exit-code mapping and the declared `[cli]` surface. What an ordinary batch application wants as much as a developer tool does. Console output is not here — it is a property of the process, and lives in `rn-forge-commons`. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | `rn_forge.tooling` | The file-owning developer tooling: local JSON state, the generation engine, and install mechanics. Depends on `rn-forge-cli`; never a runtime dependency of a deployed app. |
| [`rn-forge-web`](packages/rn-forge-web) | `rn_forge.web` | Framework-agnostic HTTP/API primitives — the wire semantics an application promises its callers: W3C Trace Context, RFC 9457 problem details, ETag preconditions, AIP-158 pagination, idempotency, readiness, ASGI middleware, the auth contract, and a framework-free conformance table. Depends on `rn-forge-commons` and nothing else. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (basic/JWT/SAML), DRF views/serializers/exceptions, a typed settings facade. |
| [`rn-forge-fastapi`](packages/rn-forge-fastapi) | `rn_forge.fastapi` | FastAPI adapters over `rn-forge-web`: problem handlers, the OpenAPI error-type repair and `operationId` convention, pagination/idempotency/`If-Match` dependencies, a health router and the auth binding. Makes no wire decision of its own. |
| [`rn-forge-devops`](packages/rn-forge-devops) | `rn_forge.devops` | CI and release automation for rn-forge repositories in any language, run with uv: the `rn-forge-devops` command plans each CI job's matrix from the workspace manifests and gates releases on their checks. Depends on `packaging` and no other rn-forge package; a CI tool, not an application dependency. |
| [`rn-forge-data`](packages/rn-forge-data) | `rn_forge.data` | Excel and tabular data helpers over `rn-forge-commons`. Base dependencies are `openpyxl` and `tablib[xlsx]`; the `pandas` extra adds the pandas adapter. |
| [`rn-forge-sqlalchemy`](packages/rn-forge-sqlalchemy) | `rn_forge.sqlalchemy` | Async SQLAlchemy models, upsert and keyset pagination over `rn-forge-web`: `Base`, `UTCDateTime`, audit and version mixins, `update_versioned`, `upsert`, `keyset`. PostgreSQL and SQLite. |

## Import boundaries

The boundaries between these packages are executable, not conventional.
[`.importlinter`](.importlinter) states eleven contracts and
`uv run lint-imports` proves them; CI gates every other job on it.

1. `rn_forge.commons` never reaches into `rn_forge.cli` or `rn_forge.tooling`
   and never imports Typer. Jinja and the Markdown parsers enter only through
   `rn_forge.commons.text`, and `rn_forge.commons.generation` and `text` are
   imported directly, never by commons' core or facade.
1. `rn_forge.cli` never imports `rn_forge.tooling` or Jinja — a batch
   application takes the command-line layer without the file-owning machinery
   (ADR-0002).
1. The three libraries layer strictly: `tooling` → `cli` → `commons`.
1. `rn_forge.django`'s runtime surface imports none of them. Only
   `rn_forge.django.codegen` may, and only with the (not yet built) `codegen`
   extra installed.
1. `rn_forge.web` imports no web framework (`django`, `fastapi`, `starlette`,
   `rest_framework`) and neither `rn_forge.cli` nor `rn_forge.tooling` — it
   ships into an ASGI server and has no business reaching the command-line or
   file-owning layers.
1. The framework packages layer on top of it: `django` → `web` → `commons`,
   `fastapi` → `web` → `commons` and `sqlalchemy` → `web` → `commons`, as
   independent siblings, so none may import another.
1. `rn_forge.fastapi` imports neither `rn_forge.django`, `rn_forge.cli`,
   `rn_forge.tooling` nor Jinja. Only its (not yet built)
   `rn_forge.fastapi.codegen` may.
1. `rn_forge.sqlalchemy` imports neither framework package nor `fastapi`,
   `starlette`, `django` or `rest_framework`.
1. `rn_forge.devops` imports no other `rn_forge` package: CI tooling for any
   language's repository carries no rn-forge dependency (ADR-0012).
1. `rn_forge.devops.ci`, the core, imports neither the uv nor the GitHub Actions
   adapter.
1. `rn_forge.data`, the core, never imports the `rn_forge.data.pandas` adapter,
   and the framework packages layer over it as siblings of `rn_forge.web`.

There are deliberately **no compatibility re-exports** in any direction: a shim
would satisfy a caller and reverse the dependency.

All packages ship a `py.typed` marker and are type-checked in strict mode.

## Design principles

1. **Standards and proven libraries first.** Depend on a maintained library
   rather than reimplementing it; follow the RFC or W3C standard where one
   exists; wrap only to give one design language, never to extend.
   ([ADR-0001](docs/adr/ADR-0001.md))
1. **Package boundaries are non-negotiable.** Code is placed by what its API
   contains, protocols sit low and adapters beside their technology, and
   runtime packages never import tooling. ([ADR-0002](docs/adr/ADR-0002.md))
1. **Situational dependencies live behind extras**, outside the package facade.
   ([ADR-0003](docs/adr/ADR-0003.md))
1. **Packages release independently, as pinned git tags.** Each package has its
   own version and tag; nothing is published to PyPI.
   ([ADR-0004](docs/adr/ADR-0004.md))
1. **pykit is upstream.** Applications are built on these libraries rather than
   re-deriving them, so apps sharing pykit share logic and read alike.

These hold for every existing package and for every future one — new modules,
new packages, new extras. When a plan or a change conflicts with one of them,
the principle wins unless the deviation is written down with its reason. The
linked decisions state each rule in full.

## Installing a package

A consumer declares pykit's package index once and requires packages by version
range:

```toml
dependencies = ["rn-forge-commons>=0.7.0,<0.8"]

[[tool.uv.index]]
name = "rn-forge"
url = "https://rn-forge.github.io/pykit/simple/"
```

The alternative is a pinned git direct URL with its subdirectory:

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
]
```

The [consuming guide](docs/guides/consuming-packages.md) covers both. The
[release pages](docs/releases/index.md) record which tags exist. Inside this
workspace, `[tool.uv.sources]` resolves every package to the local checkout
instead.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --all-extras
```

## Development

The [development guide](docs/guides/development.md) lists the setup, test, lint,
type-check, import-boundary and documentation commands. All packages build with
`uv_build`, with `module-name` mapped to their `rn_forge.*` namespace package.

## Documentation

The [published site](https://rn-forge.github.io/pykit/) combines every package's
docs with the root docs, built from `main`. Each package's docs for its released
versions are published separately, at
`https://rn-forge.github.io/pykit/packages/<package>/latest/`
([ADR-0009](docs/adr/ADR-0009.md)).

**Using the packages.** Each package's `README.md` and `docs/` hold its usage
guides, API reference and changelog, and build as a standalone site. Start with
[choosing packages](docs/guides/choosing-packages.md), then the package:
[`rn-forge-commons`](packages/rn-forge-commons),
[`rn-forge-cli`](packages/rn-forge-cli),
[`rn-forge-tooling`](packages/rn-forge-tooling),
[`rn-forge-web`](packages/rn-forge-web),
[`rn-forge-django`](packages/rn-forge-django),
[`rn-forge-fastapi`](packages/rn-forge-fastapi),
[`rn-forge-sqlalchemy`](packages/rn-forge-sqlalchemy),
[`rn-forge-devops`](packages/rn-forge-devops) or
[`rn-forge-data`](packages/rn-forge-data).

**Maintaining the workspace.** [`docs/`](docs/index.md) holds what spans
packages: the [spec board](docs/specs/index.md) of current and planned work
(start here), [decisions](docs/adr/index.md),
[architecture](docs/architecture/index.md), [guides](docs/guides/index.md),
[runbooks](docs/runbooks/index.md) and [releases](docs/releases/index.md).
[`docs/_structure.md`](docs/_structure.md) says where a new page belongs.
[CLAUDE.md](CLAUDE.md) is the agent-instruction file; it points here rather than
restating any of it.
