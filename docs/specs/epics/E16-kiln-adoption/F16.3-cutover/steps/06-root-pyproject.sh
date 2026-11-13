#!/usr/bin/env bash
# S16.3.1 step 6: root pyproject.
set -euo pipefail
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
cp "$REF/pyproject.toml" pyproject.toml
python3 -I - <<'PY'
import pathlib
import re

F = pathlib.Path("pyproject.toml")
text = F.read_text()


def swap(old, new):
    global text
    assert text.count(old) == 1, old
    text = text.replace(old, new)


# [project]: repository metadata pykit had and the reference dropped.
swap(
    'version = "0.1.0"\n',
    'version = "0.1.0"\n'
    'description = "Development kit for python programming"\n'
    'readme = "README.md"\n'
    'authors = [{ name = "Rohit Narayanan", email = "rohit.nn@gmail.com" }]\n',
)

# pyright: pykit's strictness, and the two guide examples whose frameworks the
# workspace does not install. Keys sorted alphabetically; a blank line before
# the table (the reference has none after the last [tool.uv.sources.*] table).
swap(
    'workspace = true\n\n[tool.pyright]\ninclude = ["packages"]\n'
    'reportMissingTypeStubs = false\ntypeCheckingMode = "strict"\nvenv = ".venv"\nvenvPath = "."\n',
    'workspace = true\n\n[tool.pyright]\n'
    'ignore = [\n'
    '    "tests",\n'
    '    "**/tests",\n'
    "    # The two framework examples in rn-forge-web's guides are documentation:\n"
    "    # they import Django/DRF and FastAPI, which this workspace deliberately does not\n"
    "    # install for that package. The framework-free asgi_app.py beside them is NOT\n"
    "    # excluded — it is executed by the test suite and is typechecked like any source.\n"
    '    "packages/rn-forge-web/docs/guides/examples/django_app.py",\n'
    '    "packages/rn-forge-web/docs/guides/examples/fastapi_app.py",\n'
    "]\n"
    'include = ["packages"]\n'
    "reportMissingTypeStubs = false\n"
    'reportUnnecessaryTypeIgnoreComment = "error"\n'
    'typeCheckingMode = "strict"\n'
    'venv = ".venv"\n'
    'venvPath = "."\n',
)

# pytest markers, and the workspace-wide scaffold suite that ci.yml reads.
swap(
    'addopts = "-ra --import-mode=importlib"\ntestpaths = ["packages"]\n',
    'addopts = "-ra --import-mode=importlib"\ntestpaths = ["packages"]\n'
    "markers = [\n"
    '    "unit: fast isolated tests",\n'
    '    "integration: tests that exercise database-backed behavior",\n'
    '    "postgres: needs a PostgreSQL DSN in RN_FORGE_TEST_POSTGRES_DSN",\n'
    '    "broker: needs Keycloak at RN_FORGE_AUTH_KEYCLOAK_URL (rn-forge-auth)",\n'
    '    "scaffold: installs built wheels into a scaffolded application (slow)",\n'
    '    "security_control: demonstrates the security control with the given rn_forge.auth.conformance case ID",\n'
    "]\n\n"
    "[tool.workspace-ci.suites]\n"
    "# Each suite is its own job over the whole workspace. Package jobs deselect the\n"
    "# scaffold tests through each member's own pytest addopts.\n"
    'scaffold = ["-q", "-m", "scaffold"]\n',
)

# ruff: Bandit, the two import/bugbear tables src needs, and the tests' ignores.
swap(
    '[tool.ruff.lint.per-file-ignores]\n"**/tests/*" = ["ANN", "D", "PLR2004", "S101"]\n',
    "[tool.ruff.lint]\n"
    "# Bandit's checks, including the Django ones (S308, S703).\n"
    'extend-select = ["S"]\n\n'
    "[tool.ruff.lint.isort]\n"
    "# ruff otherwise sorts these frameworks as first-party, after the rn_forge subpackages that share their names.\n"
    'known-third-party = ["django", "fastapi", "sqlalchemy"]\n\n'
    "[tool.ruff.lint.flake8-bugbear]\n"
    "extend-immutable-calls = [\n"
    '    "fastapi.Body",\n    "fastapi.Depends",\n    "fastapi.Query",\n    "fastapi.Security",\n'
    "]\n\n"
    "[tool.ruff.lint.per-file-ignores]\n"
    "# Debt, not policy: S16.3.9 replaces ALL with kiln's four ignores and the\n"
    "# justified Bandit test rules.\n"
    '"**/tests/*" = ["ALL"]\n'
    "# Repository tooling outside packages/, which is what the source scan covers.\n"
    '"conftest.py" = ["S"]\n'
    '".github/scripts/*" = ["S"]\n',
)

# dependency groups: the reference's, plus pykit's real dependencies.
a = text.index("[dependency-groups]")
text = text[:a] + '''[dependency-groups]
dev = [
    { include-group = "workspace" },
    "actionlint-py>=1.7",
    "aiosqlite>=0.21",
    "alembic>=1.20.1",
    "assertpy>=2.35",
    "asyncpg>=0.30",
    "coverage[toml]>=7.6",
    "django-stubs>=6.1.2",
    "google-yamlfmt>=0.21.0",
    "import-linter>=2.15",
    "opentelemetry-instrumentation-asgi>=0.65b0",
    "opentelemetry-sdk>=1.44",
    "pandas-stubs>=3.0.5",
    "pip-audit>=2.10",
    "pip-licenses>=5",
    "psycopg[binary]>=3.3.5",
    "pyright>=1.1",
    "pytest>=9.1",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.1",
    "pytest-django>=4.12.0",
    "pytest-randomly>=4.1.0",
    "rn-forge-data[pandas]",
    "ruff>=0.17.1",
    "taplo>=0.9",
    "types-authlib>=1.8.0",
    "zizmor>=1.31",
]
docs = [
    "mdformat>=1.0.0",
    "mdformat-front-matters>=2.0.0",
    "mdformat-gfm>=0.4",
    "mdformat-mkdocs>=5.3.0",
    "mike>=2.1.3",
    "mkdocs>=1.6.1",
    "mkdocs-material>=9.6",
    "mkdocs-monorepo-plugin>=1.1",
    "mkdocstrings[python]>=0.30",
]
workspace = [
    "rn-forge-auth[oidc]",
    "rn-forge-cli",
    "rn-forge-commons[all]",
    "rn-forge-devops",
    "rn-forge-django[all]",
    "rn-forge-fastapi[sse,transfer]",
    "rn-forge-sqlalchemy",
    "rn-forge-tooling",
    "rn-forge-web[security]",
]
'''
# one blank line precedes every table
assert not re.search(r"[^\n]\n\[", text), "a table follows a non-blank line"
F.write_text(text)
PY
