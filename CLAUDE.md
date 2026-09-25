# CLAUDE.md

Agent instructions for work in this repository.

This file is **agent instructions only**. Anything that describes the software itself — what a
package holds, how a subsystem works, how to configure it — lives in that package's `README.md`
and `docs/`, and is linked from here. When the two disagree, the package's own docs win: they are
built (`mkdocs --strict`) and the docstrings under them are checked. Do not restate package
architecture here; it drifts.

## Start here in a new session

[The spec board](docs/specs/index.md) is the current status entry point. Read it before starting
work. Use [root routing](docs/_structure.md) to place documentation and [the reader index](docs/index.md)
to find published content. [Decisions](docs/adr/index.md) record durable constraints;
[history and the migration ledger](docs/plans/context.md) preserve plan evidence.

## Orientation

| Read this | For |
| --- | --- |
| [README.md](README.md) | The package table, executable import contracts, design principles and pinned-tag distribution model |
| [`packages/<pkg>/README.md`](packages) | What that package holds, module by module, and how to depend on it |
| `packages/<pkg>/docs/guides/` | How to use a subsystem (Django settings, models, auth, DRF views; commons console, logging, config; the CLI's declared surface) |
| [`.importlinter`](.importlinter) | The import boundaries, as the executable source of truth |
| [Root architecture](docs/architecture/index.md) | Current package relationships and cross-package behavior |
| [Specifications](docs/specs/index.md) | Live work, acceptance, release gates and open questions |
| [Decisions](docs/adr/index.md) | Durable cross-package choices |
| [History](docs/plans/context.md) | Source plans, supersession and the migration ledger |

Two rules from the README that constrain almost every change, repeated here because violating them
is silent until CI:

- **The design principles govern new work.** When a plan or a change conflicts with one, the
  principle wins unless the deviation is written down with its reason.
- **There are no compatibility re-exports, in any direction.** A shim would satisfy a caller and
  reverse a dependency. When moving a symbol across a package boundary, move it; do not alias it.

## Commands

Run from the repo root unless testing a single package.

```bash
uv sync --all-extras                      # install workspace + all optional extras
uv run pytest                             # run tests across the workspace
uv run pytest packages/rn-forge-cli       # run one package's tests
uv run pytest -k test_name                # run a single test by name/keyword
uv run pytest -m unit                     # rn-forge-django/web: fast isolated tests
uv run pytest -m integration              # rn-forge-django only: DB-backed tests
uv run ruff check .                       # lint
uv run ruff format .                      # format
uv run pyright                            # type check (strict mode, see below)
uv run lint-imports                       # enforce .importlinter package boundaries
```

Per-package commands work the same way with `--directory packages/<pkg>` or by `cd`-ing into the
package first. Each package's `dev`/`docs` dependency groups self-reference their own `all`
(django) / `excel` (commons) extra, so a `--group dev` sync always exercises every optional code
path instead of silently skipping `pytest.importorskip`-gated tests.

## Constraints that bite

### Type checking

Root `pyproject.toml` runs Pyright in `strict` mode over `include = ["packages"]`, ignoring
`tests` and the two framework examples in `rn-forge-web/docs/adoption/examples/` (they import
Django and FastAPI, which that package deliberately does not install; the framework-free
`asgi_app.py` beside them **is** typechecked, and the test suite runs it against the conformance
table). Test code is intentionally excluded; library source under `src/` is not — new source must
satisfy strict mode (explicit types, no untyped `Any` leakage across public APIs).

### Docs

Each of the seven packages has an MkDocs site (`packages/<pkg>/mkdocs.yml`), and the root
`mkdocs.yml` includes them all via the monorepo
plugin. Build with `uv run --group docs mkdocs build --strict` from a package directory, or from
the repo root for the combined site. Per-package builds are strict, so a cross-package link fails
the build — reference the other package by name instead of linking into it. Docstrings are the doc
source, not just IDE hints; keep them accurate.

**Docstrings describe the contract, nothing else.** What a symbol does, its arguments, return
value, raised exceptions, and a short example where it helps. Keep out of them:

- design justification and motivation ("so that…", "rather than…", "for a document whose author
  should…"), history, plan or ADR references, and self-assessment of the code;
- examples tied to a specific consumer (go-task, kiln) when a generic one reads the same.

Where that material belongs:

- **Why a user would choose it, and how subsystems fit together** → the package's
  `docs/guides/`.
- **Why a non-obvious piece of code is written the way it is** → a `#` comment beside that code,
  for maintainers. Straightforward logic needs no comment at all.
- **How the workspace got its shape** → `docs/plans/`.

**Code comments explain the non-obvious *why*, and stay smaller than the code they explain.**

- Comment a constraint the code cannot show: an ordering that matters, a library quirk, a
  deliberately rejected alternative that looks simpler. Do not narrate what the next line does.
- One or two lines is the norm. A comment longer than the block it sits on means the reasoning
  belongs in `docs/` (link or name the guide) or the code should be clearer — rename, extract a
  well-named helper — rather than explained.
- No history ("previously…", "after the review…"), plan references or TODO essays; those go in
  `docs/plans/` or an issue.
- When code changes, fix or delete its comment in the same edit. A stale comment is worse than none.

Apply both rules to every docstring and comment you add or change, and check for them when
reviewing a diff.

Each package has a curated `src/rn_forge/<pkg>/__init__.py` facade — re-export new public symbols
there. Modules gated behind an optional extra are deliberately excluded from the facade; import
them directly. Public class names do not encode their module grouping, so moving a module never
moves a class name.

### Testing

- Tests live in each package's `tests/`, mirroring the `src/rn_forge/<pkg>/` layout (e.g.
  `tests/fs/test_paths.py` tests `src/rn_forge/commons/fs/paths.py`). When a module moves, its
  test module moves with it.
- A test module that has to be imported *by name* (a `--policy` reference, say) needs an
  unambiguous alias rather than `tests.<...>` — see
  `rn-forge-tooling/tests/cli/test_lifecycle_commands.py`.
- Tests run in pytest's `importlib` import mode, set in the root `pyproject.toml` and in every
  package's. No `tests/` directory has an `__init__.py`, and test module basenames need not be
  unique across packages. Do **not** add an `__init__.py` under `tests/`: it makes that package's
  tests importable as `tests`, which collides with any other package that does the same.
- A test module cannot import another test module or `conftest.py`. A helper shared by several
  test modules is a fixture in `conftest.py`, or, if it is generic, belongs in
  `rn_forge.commons.testing`. A test-only Django model is declared in the test module that uses it.
- A root-level `uv run pytest` reads only the root `[tool.pytest.ini_options]`, not a package's.
  That is why `rn-forge-web` marks its async tests with an explicit `@pytest.mark.asyncio` rather
  than relying on its own `asyncio_mode = "auto"`, and why the `unit` and `integration` markers are
  registered at the root as well as in the packages that use them.
- `pytest-randomly` randomizes order in every package — do not rely on cross-test ordering.
- Tests are excluded from ruff's lint rules (`per-file-ignores` = `ALL` for `**/tests/*`) and from
  Pyright's strict checking.
