# Handoff to kiln: discovered workspace CI

pykit's CI no longer names its packages. One script reads the uv workspace and plans every job, so the workflow can be copied unchanged into any uv monorepo whose packages are released separately. This note is for bringing it into kiln's golden templates. The design and its reasons are in pykit's `docs/specs/epics/E14-workspace-ci/F14.1-discovered-pipeline.md`.

## Files to copy verbatim

| pykit file | Template file | Notes |
| --- | --- | --- |
| `.github/workflows/main.yml` | same path | Has no repository-specific values. |
| `.github/scripts/workspace_ci.py` | same path | Standard library only, except `smoke`, which the workflow runs with `packaging`. |

Retire any per-package job template, reusable package workflow, or `changed_packages.py` or `check_django_extra.py` copy.

## What a generated repository provides

Required:

- A root `pyproject.toml` with `[tool.uv.workspace].members` (globs and `exclude` work) and a committed `uv.lock`. CI runs `uv sync --all-packages --all-extras --locked`.
- In each member, `[project].name` and `version`. Set `[tool.uv.build-backend].module-name` when the import name is not the project name with `-` changed to `_`.
- Package tests under `<member>/tests/`. Sonar only lists test directories that exist.

Optional, each turned on by the file existing:

| File | Turns on |
| --- | --- |
| `.importlinter` | The `lint-imports` gate |
| `sonar-project.properties` | The `sonar` job. Keep only the project key, organization and settings; do not list sources or tests, because CI passes them. Needs the `SONAR_TOKEN` secret. |
| `mkdocs.yml` (root), `<member>/mkdocs.yml` | The `docs` job: `mike` sites per package, then the root site built with `--strict`. Needs a `docs` dependency group and GitHub Pages. |

Optional `[tool.workspace-ci]` settings:

```toml
# root pyproject.toml
[tool.workspace-ci]
pytest-args = ["-m", "not slow"]            # every package's pytest run

[tool.workspace-ci.suites]                   # one workspace-wide pytest job per key
e2e = ["-q", "-m", "e2e"]

# a member's pyproject.toml
[tool.workspace-ci.postgres]
env = "MYPKG_TEST_DATABASE_URL"              # receives postgresql://ci:ci@localhost:5432/ci

[tool.workspace-ci.smoke]                    # install from built wheels, one extra at a time
setup = "tests/smoke_setup.py"               # optional; runs before the imports
modules = ["my_pkg"]                         # imported in every smoke run
[tool.workspace-ci.smoke.extras]
redis = ["my_pkg.cache.redis"]               # one job per extra
```

pykit's own settings are in its root `pyproject.toml` and in `packages/rn-forge-django/pyproject.toml`, which uses every package-level setting.

## Assumptions baked into the workflow

- Tags are `<project-name>-v<version>`, each with a GitHub Release. Tagging happens only on a push to `main`.
- Packages are installed from `git+<server>/<repo>@<tag>#subdirectory=<member dir>`, derived from the run. There is no PyPI publishing.
- A change under `docs/` selects no package; any other change outside the members selects every package. The prefix list is `UNSCOPED` in the script.
- The docs job's step that copies package sites from `gh-pages` into the root site expects members under `packages/`.
- The PostgreSQL service is `postgres:17`, and it is the only service supported.

## Setting up a repository

- Branch protection: make **`ci-ok`** the only required check. Matrix job names such as `verify (<name>)` change as packages are added.
- The workflow needs `contents: write` for tagging, and Pages permissions for the docs job. Both are already declared per job.

## Checking a generated repository

```bash
python3 .github/scripts/workspace_ci.py plan        # every package; prints each job's matrix
actionlint .github/workflows/main.yml
uv run --no-project --with packaging python .github/scripts/workspace_ci.py smoke <package> <extra>
```

After that, a pull request run should show one `verify` job per changed package and its dependents, with `ci-ok` passing.
