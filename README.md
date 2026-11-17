# pykit

Development kit for Python programming. A
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Purpose |
| -- | -- |
| [`rn-forge-commons`](packages/rn-forge-commons) | Runtime-neutral utilities, protocols, logging and console output. |
| [`rn-forge-cli`](packages/rn-forge-cli) | The shared command-line layer: Typer application, standard options and exit codes. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | Install and lifecycle verbs for command-line developer tools. |
| [`rn-forge-web`](packages/rn-forge-web) | Framework-agnostic HTTP wire contracts and a conformance table. |
| [`rn-forge-auth`](packages/rn-forge-auth) | Authentication and authorization primitives; OIDC and Redis behind extras. |
| [`rn-forge-django`](packages/rn-forge-django) | Django and DRF adapters over the web and auth contracts. |
| [`rn-forge-fastapi`](packages/rn-forge-fastapi) | FastAPI adapters over the web and auth contracts. |
| [`rn-forge-devops`](packages/rn-forge-devops) | Release commands for the pykit workspace; a CI tool, not an application dependency. |
| [`rn-forge-data`](packages/rn-forge-data) | Excel and tabular data helpers; a pandas adapter behind an extra. |
| [`rn-forge-sqlalchemy`](packages/rn-forge-sqlalchemy) | Async SQLAlchemy models, upsert and keyset pagination. |

[Choosing packages](docs/guides/choosing-packages.md) says which to take;
[workspace boundaries](docs/architecture/workspace.md) explains how they depend
on each other.

## Import boundaries

The boundaries between packages are executable: [`.importlinter`](.importlinter)
states them, `task lint` proves them and CI gates every other job on it.
[Workspace boundaries](docs/architecture/workspace.md) explains the graph and
the rules. There are no compatibility re-exports in any direction
([ADR-0002](docs/adr/ADR-0002.md)).

Every package ships a `py.typed` marker and is type-checked in strict mode.

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
   requires its dependencies by version range; every package is published to
   PyPI. ([ADR-0004](docs/adr/ADR-0004.md))
1. **pykit is upstream.** Applications are built on these libraries rather than
   re-deriving them, so apps sharing pykit share logic and read alike.

These hold for every existing package and for every future one — new modules,
new packages, new extras. When a plan or a change conflicts with one of them,
the principle wins unless the deviation is written down with its reason. The
linked decisions state each rule in full.

## Installing a package

Every package is published to PyPI and required by version range, for example
`rn-forge-commons>=0.9,<0.10`. The
[consuming guide](docs/guides/consuming-packages.md) covers ranges, exact pins
and git direct URLs, and the [release pages](docs/releases/index.md) record
which tags exist.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
task setup
```

## Development

The [development guide](docs/guides/development.md) lists the setup, test, lint,
type-check, import-boundary and documentation commands.

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
[choosing packages](docs/guides/choosing-packages.md), then the package's README
from the table above.

**Maintaining the workspace.** [`docs/`](docs/index.md) holds what spans
packages: the [spec board](docs/specs/index.md) of current and planned work
(start here), [decisions](docs/adr/index.md),
[architecture](docs/architecture/index.md), [guides](docs/guides/index.md),
[runbooks](docs/runbooks/index.md) and [releases](docs/releases/index.md).
[`docs/_structure.md`](docs/_structure.md) says where a new page belongs.
[AGENTS.md](AGENTS.md) holds what an agent needs beyond this file; `CLAUDE.md`
imports it.
