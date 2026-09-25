# Developing pykit

This guide gives maintainers the workspace's local validation commands. Run them from the repository root unless a package-specific command says otherwise.

**Status:** done

**Owner:** pykit.

The repository is a uv workspace with seven packages. `uv sync --all-extras` installs the local development environment. Package code targets Python 3.14 or later.

| Check | Command |
| --- | --- |
| All tests | `uv run pytest` |
| One package's tests | `uv run pytest packages/rn-forge-cli` |
| Ruff lint | `uv run ruff check .` |
| Ruff formatting check | `uv run ruff format --check .` |
| Strict type check | `uv run pyright` |
| Import boundaries | `uv run lint-imports` |
| Combined documentation | `uv run --group docs mkdocs build --strict` |

Each package also has a standalone MkDocs site. Build it from that package's directory with `uv run --group docs mkdocs build --strict`. Root MkDocs includes all seven sites; a combined build does not establish that each standalone site resolves its own links. Use a temporary `--site-dir` when preserving an existing preview.

Tests live under each package's `tests/` tree. The root pytest configuration uses `importlib` import mode and registers `unit`, `integration` and `postgres` markers. Source under `packages/` is checked by Pyright in strict mode; tests and two framework-specific web documentation examples are excluded. The framework-neutral ASGI example remains checked.

For a new package, follow [Adding a package](../runbooks/adding-a-package.md). The [workspace boundaries](../architecture/workspace.md) describe the import contracts that the new package must respect.
