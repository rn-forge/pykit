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
to find published content.

Do not start or elaborate an epic or feature tagged `deferred`, such as the Azure package (E7), unless
the owner asks. Entry criteria describe when the owner may schedule it, not permission to begin. The
same holds for ideas parked in [the ideas list](docs/specs/ideas.md).

## Orientation

| Read this | For |
| --- | --- |
| [README.md](README.md) | The package table, executable import contracts, design principles and pinned-tag distribution model |
| [`packages/<pkg>/README.md`](packages) | What that package holds, module by module, and how to depend on it |
| `packages/<pkg>/docs/guides/` | How to use a subsystem (Django settings, models, auth, DRF views; commons console, logging, config; the CLI's declared surface) |
| [`.importlinter`](.importlinter) | The import boundaries, as the executable source of truth |
| [Root architecture](docs/architecture/index.md) | Current package relationships and cross-package behavior |
| [Decisions](docs/adr/index.md) | Durable cross-package constraints |
| [Development guide](docs/guides/development.md) | Setup and validation commands (per-package and single-test forms), docs builds, test and type-check configuration |

Two rules violated silently until CI:

- **The design principles govern new work** ([ADR-0001](docs/adr/ADR-0001.md)): a conflicting
  plan or change loses unless the deviation is written down with its reason.
- **No compatibility re-exports** ([ADR-0002](docs/adr/ADR-0002.md)): when a symbol crosses a
  package boundary, move it; do not alias it.

## Constraints that bite

### Source

- Pyright runs in strict mode over `packages/`; its exclusions are the `ignore` list in the root
  `pyproject.toml`. New library source must satisfy strict mode (explicit types, no untyped `Any`
  leakage across public APIs).
- Re-export new public symbols from the package's curated `src/rn_forge/<pkg>/__init__.py` facade.
  Modules gated behind an optional extra stay out of it and are imported directly
  ([ADR-0003](docs/adr/ADR-0003.md)). Public class names do not encode their module grouping, so
  moving a module never moves a class name.

### Docs

Per-package MkDocs builds are strict, so a cross-package link fails the build — reference the other
package by name instead of linking into it. Build both the package site and the combined site (see
the development guide). Docstrings are the doc source, not just IDE hints; keep them accurate.

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
- **How the workspace got its shape** → the commit message.

**Code comments explain the non-obvious *why*, and stay smaller than the code they explain.**

- Comment a constraint the code cannot show: an ordering that matters, a library quirk, a
  deliberately rejected alternative that looks simpler. Do not narrate what the next line does.
- One or two lines is the norm. A comment longer than the block it sits on means the reasoning
  belongs in `docs/` (link or name the guide) or the code should be clearer — rename, extract a
  well-named helper — rather than explained.
- No history ("previously…", "after the review…"), plan references or TODO essays; those go in
  the commit message or an issue.
- When code changes, fix or delete its comment in the same edit. A stale comment is worse than none.

Apply both rules to every docstring and comment you add or change, and check for them when
reviewing a diff.

### Testing

- Tests live in each package's `tests/`, mirroring the `src/rn_forge/<pkg>/` layout (e.g.
  `tests/fs/test_paths.py` tests `src/rn_forge/commons/fs/paths.py`). When a module moves, its
  test module moves with it.
- A test module that has to be imported *by name* (a `--policy` reference, say) needs an
  unambiguous alias rather than `tests.<...>` — see
  `rn-forge-tooling/tests/cli/test_lifecycle_commands.py`.
- Do **not** add an `__init__.py` under `tests/`. Tests run in `importlib` mode; an `__init__.py`
  makes that package's tests importable as `tests`, colliding with any other package that does
  the same.
- A test module cannot import another test module or `conftest.py`. A helper shared by several
  test modules is a fixture in `conftest.py`, or, if it is generic, belongs in
  `rn_forge.commons.testing`. A test-only Django model is declared in the test module that uses it.
- A root-level `uv run pytest` reads only the root `[tool.pytest.ini_options]`. Mark async tests
  with an explicit `@pytest.mark.asyncio` rather than relying on a package's `asyncio_mode`, and
  register any new marker at the root as well as in the package that uses it.
- `pytest-randomly` randomizes order in every package — do not rely on cross-test ordering.
