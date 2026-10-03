# Developing pykit

The workspace's local setup and validation commands. Run them from the repository root unless a command says otherwise.

## Setup

The repository is a uv workspace with seven packages. Install every package and every optional extra with:

```bash
uv sync --all-extras
```

Package code targets Python 3.14 or later, and the floor stays at `>=3.14` across the workspace; lowering it would be a workspace decision, not a package one. Use a patch release: on a 3.14 release candidate, `mkdocstrings`' pydantic support fails (`_eval_type() got an unexpected keyword argument 'prefer_fwd_module'`) and every docs build exits 1. Python 3.14.2 and later build cleanly.

## Commands

| Check | Command |
| --- | --- |
| All tests | `uv run pytest` |
| One package's tests | `uv run pytest packages/rn-forge-cli` |
| One test by name or keyword | `uv run pytest -k test_name` |
| Fast isolated tests (`rn-forge-django`, `rn-forge-web`) | `uv run pytest -m unit` |
| Database-backed tests (`rn-forge-django`) | `uv run pytest -m integration` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .`; add `--check` to report without writing |
| Strict type check | `uv run pyright` |
| Import boundaries | `uv run lint-imports` |
| Combined documentation | `uv run --group docs mkdocs build --strict` |

Per-package commands work the same way with `--directory packages/<pkg>`, or from inside the package directory. Each package's `dev` and `docs` dependency groups include its own optional extras, so a `--group dev` sync runs every optional code path instead of skipping `pytest.importorskip`-gated tests.

## Sonar feedback

Connect SonarQube for IDE to the project's SonarCloud server (connected mode) for instant rule feedback while editing. Taint analysis and the quality gate need a server analysis, which the IDE cannot certify.

To analyze the working tree before pushing:

```bash
python3 .github/scripts/sonar_local.py --dry-run
python3 .github/scripts/sonar_local.py
```

The first command prints the target branch and the exact test and scanner commands, which use the same packages, coverage arguments and sources as CI; it needs no token and runs nothing. The second runs the workspace coverage tests, then uploads the code and results to SonarCloud and exits with the quality gate's status. A full scan needs:

- network access, and a non-`main` branch on a plan with branch analysis; the script refuses `main`, and `--branch` must match the checked-out branch unless HEAD is detached;
- a SonarCloud token provided by the project owner, exported as `SONAR_TOKEN`;
- the official [SonarScanner CLI](https://docs.sonarsource.com/sonarqube-cloud/advanced-setup/ci-based-analysis/sonarscanner-cli/) on `PATH`. The repository adds no dependency for it.

A scan of uncommitted changes is not CI evidence for a commit.

## Documentation builds

Each package also has a standalone MkDocs site. Build it from that package's directory with `uv run --group docs mkdocs build --strict`. The root site includes all seven, but a combined build does not show that each standalone site resolves its own links, so check both. Use a temporary `--site-dir` to keep an existing preview.

## Tests and types

Tests live under each package's `tests/` tree. The root pytest configuration uses `importlib` import mode and registers the `unit`, `integration` and `postgres` markers. Source under `packages/` is checked by Pyright in strict mode; tests and two framework-specific web documentation examples are excluded, while the framework-neutral ASGI example is checked.

For a new package, follow [Adding a package](../runbooks/adding-a-package.md). The [workspace boundaries](../architecture/workspace.md) describe the import contracts it must respect.
