# pykit

Development kit for Python programming. A
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| -- | -- | -- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | Runtime-neutral utilities, grouped by kind of mechanism: `lang` (collections, dataclasses, reflection, values), `fs` (paths, hashing, locks, blocks, documents, state), `generation` (plan, diff and atomic apply of owned files), `data` (Excel/pandas), `text` (templates, Markdown — each behind an extra), `logging`, `runtime` (environment, subprocess, tasks, plugins) and `integration` (messaging/object/secret protocols, resilience), plus config, exceptions, findings and testing helpers. No web framework. |
| [`rn-forge-cli`](packages/rn-forge-cli) | `rn_forge.cli` | The shared command-line layer: `CliApp` (a `typer.Typer` subclass), the standard option set, the error-to-exit-code mapping and the declared `[cli]` surface. What an ordinary batch application wants as much as a developer tool does. Console output is not here — it is a property of the process, and lives in `rn-forge-commons`. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | `rn_forge.tooling` | Developer-tool lifecycle verbs and install mechanics: `$RNF_HOME`, release fetching and verification, transactional install/upgrade/uninstall. Depends on `rn-forge-cli`; never a runtime dependency of a deployed app. |
| [`rn-forge-web`](packages/rn-forge-web) | `rn_forge.web` | Framework-agnostic HTTP/API primitives — the wire semantics an application promises its callers: W3C Trace Context, RFC 9457 problem details, ETag preconditions, AIP-158 pagination, idempotency, readiness, ASGI middleware, the auth wire contract (`Credentials`, the `Authorization` parser, the `WWW-Authenticate` challenge), and a framework-free conformance table. Depends on `rn-forge-commons` and nothing else. |
| [`rn-forge-auth`](packages/rn-forge-auth) | `rn_forge.auth` | Authentication and authorization primitives over `rn-forge-web`: the identity, account and authorization-context contracts, `Principal`, `Requirement`, `ScopeAuthorizer`, session, transaction and replay stores, `principal_from_claims`, `LoginFlow` and the local password and development login providers; the `oidc` extra adds the OIDC and OAuth 2.0 login provider (`OidcProvider`), back-channel logout, the OIDC token profiles (`OidcAuthenticator`, `JwtVerifier`, `IdTokenVerifier`, `LogoutTokenVerifier`) and a fake provider for tests, and the `redis` extra adds Redis stores. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (sessions, OIDC bearer, permission hooks), DRF views/serializers/exceptions, a typed settings facade. |
| [`rn-forge-fastapi`](packages/rn-forge-fastapi) | `rn_forge.fastapi` | FastAPI adapters over `rn-forge-web`: problem handlers, the OpenAPI error-type repair and `operationId` convention, pagination/idempotency/`If-Match` dependencies, a health router and the auth binding. Makes no wire decision of its own. |
| [`rn-forge-devops`](packages/rn-forge-devops) | `rn_forge.devops` | Release commands for the pykit workspace: the `rn-forge-devops` command checks internal requirements and writes the umbrella release's notes. The CI planner is kiln's `kiln-devops`. Depends on `packaging` and no other rn-forge package; a CI tool, not an application dependency. |
| [`rn-forge-data`](packages/rn-forge-data) | `rn_forge.data` | Excel and tabular data helpers over `rn-forge-commons`. Base dependencies are `openpyxl` and `tablib[xlsx]`; the `pandas` extra adds the pandas adapter. |
| [`rn-forge-sqlalchemy`](packages/rn-forge-sqlalchemy) | `rn_forge.sqlalchemy` | Async SQLAlchemy models, upsert and keyset pagination over `rn-forge-web`: `Base`, `UTCDateTime`, audit and version mixins, `update_versioned`, `upsert`, `keyset`. PostgreSQL and SQLite. |

## Import boundaries

The boundaries between these packages are executable, not conventional.
[`.importlinter`](.importlinter) states fifteen contracts, summarised by the
rules below, and the import-boundary check proves them; CI gates every other job
on it.

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
1. The framework packages layer on top of it: `django` → `auth` → `web` →
   `commons`, `fastapi` → `auth` → `web` → `commons` and `sqlalchemy` → `web`
   → `commons`, as independent siblings, so none may import another.
1. `rn_forge.auth`'s core never imports the `rn_forge.auth.oidc` adapter.
1. `rn_forge.fastapi` imports neither `rn_forge.django`, `rn_forge.cli`,
   `rn_forge.tooling` nor Jinja. Only its (not yet built)
   `rn_forge.fastapi.codegen` may.
1. `rn_forge.sqlalchemy` imports neither framework package nor `fastapi`,
   `starlette`, `django` or `rest_framework`.
1. `rn_forge.devops` imports no other `rn_forge` package: release tooling
   carries no rn-forge dependency (ADR-0012).
1. `rn_forge.data`, the core, never imports the `rn_forge.data.pandas` adapter
   (the contract names the core module, not the package that contains the
   adapter), and the framework packages layer over it as siblings of
   `rn_forge.web`.

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
1. **Packages release independently and depend on each other by range.** Each
   package has its own version and tag, and requires its dependencies by
   version range from pykit's index; nothing is published to PyPI.
   ([ADR-0004](docs/adr/ADR-0004.md))
1. **pykit is upstream.** Applications are built on these libraries rather than
   re-deriving them, so apps sharing pykit share logic and read alike.

These hold for every existing package and for every future one — new modules,
new packages, new extras. When a plan or a change conflicts with one of them,
the principle wins unless the deviation is written down with its reason. The
linked decisions state each rule in full.

## Installing a package

Every package is published to PyPI. A consumer requires one by version range:

```toml
dependencies = ["rn-forge-commons>=0.8,<0.9"]
```

Or pin a tag by git direct URL with its subdirectory:

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.8.0#subdirectory=packages/rn-forge-commons",
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
task setup
```

## Development

The [development guide](docs/guides/development.md) lists the setup, test, lint,
type-check, import-boundary and documentation commands. All packages build with
`uv_build`, with `module-name` mapped to their `rn_forge.*` namespace package.

## Working here

Everything runs through `task`; the
[development guide](docs/guides/development.md) lists the verbs and
`task validate` is the gate. A file whose first line says it was generated is
owned by kiln: edit `.rn-forge/kiln/config.toml` and run `task kiln:apply`,
never the file. The standard is
[.rn-forge/kiln/standard.md](.rn-forge/kiln/standard.md).

This README does not describe the packages. Each package's `README.md` and
`docs/` say what it holds and how it works; they are built in strict mode and
their docstrings are checked, so when the two disagree the package's own docs
win.

## Conventions

### Source

- Pyright runs in strict mode over `packages/`; its exclusions are the `ignore`
  list in the root `pyproject.toml`. New library source must satisfy strict
  mode (explicit types, no untyped `Any` leakage across public APIs).
- Re-export new public symbols from the package's curated
  `src/rn_forge/<pkg>/__init__.py` facade. Modules gated behind an optional
  extra stay out of it and are imported directly
  ([ADR-0003](docs/adr/ADR-0003.md)). Public class names do not encode their
  module grouping, so moving a module never moves a class name.

### Docs

Per-package MkDocs builds are strict, so a cross-package link fails the build —
reference the other package by name instead of linking into it. Build both the
package site and the combined site (see the
[development guide](docs/guides/development.md)). Docstrings are the doc source,
not just IDE hints; keep them accurate.

**Docstrings describe the contract, nothing else.** What a symbol does, its
arguments, return value, raised exceptions, and a short example where it helps.
Keep out of them:

- design justification and motivation ("so that…", "rather than…", "for a
  document whose author should…"), history, plan or ADR references, and
  self-assessment of the code;
- examples tied to a specific consumer (go-task, kiln) when a generic one reads
  the same.

Where that material belongs:

- **Why a user would choose it, and how subsystems fit together** → the
  package's `docs/guides/`.
- **Why a non-obvious piece of code is written the way it is** → a `#` comment
  beside that code, for maintainers. Straightforward logic needs no comment at
  all.
- **How the workspace got its shape** → the commit message.

**Code comments explain the non-obvious *why*, and stay smaller than the code
they explain.**

- Comment a constraint the code cannot show: an ordering that matters, a library
  quirk, a deliberately rejected alternative that looks simpler. Do not
  narrate what the next line does.
- One or two lines is the norm. A comment longer than the block it sits on means
  the reasoning belongs in `docs/` (link or name the guide) or the code should
  be clearer — rename, extract a well-named helper — rather than explained.
- No history ("previously…", "after the review…"), plan references or TODO
  essays; those go in the commit message or an issue.
- When code changes, fix or delete its comment in the same edit. A stale comment
  is worse than none.

Apply both rules to every docstring and comment you add or change, and check for
them when reviewing a diff.

### Testing

- Tests live in each package's `tests/`, mirroring the `src/rn_forge/<pkg>/`
  layout (e.g. `tests/fs/test_paths.py` tests
  `src/rn_forge/commons/fs/paths.py`). When a module moves, its test module
  moves with it.
- A test module that has to be imported *by name* (a `--policy` reference, say)
  needs an unambiguous alias rather than `tests.<...>` — see
  `rn-forge-tooling/tests/cli/test_lifecycle_commands.py`.
- Do **not** add an `__init__.py` under `tests/`. Tests run in `importlib` mode;
  an `__init__.py` makes that package's tests importable as `tests`, colliding
  with any other package that does the same.
- A test module cannot import another test module or `conftest.py`. A helper
  shared by several test modules is a fixture in `conftest.py`, or, if it is
  generic, belongs in `rn_forge.commons.testing`. A test-only Django model is
  declared in the test module that uses it.
- A pytest run from the repository root reads only the root
  `[tool.pytest.ini_options]`. Mark async tests with an explicit
  `@pytest.mark.asyncio` rather than relying on a package's `asyncio_mode`,
  and register any new marker at the root as well as in the package that uses
  it.
- `pytest-randomly` randomizes order in every package — do not rely on
  cross-test ordering.

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
[`rn-forge-auth`](packages/rn-forge-auth),
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
[AGENTS.md](AGENTS.md) holds what an agent needs beyond this file; `CLAUDE.md`
imports it.
