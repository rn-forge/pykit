#!/usr/bin/env bash
# S16.3.1 step 10: documents.
set -euo pipefail
python3 - <<'PY'
import pathlib

F = "`" * 3


def edit(path, old, new):
    file = pathlib.Path(path)
    text = file.read_text()
    assert text.count(old) == 1, (path, old)
    file.write_text(text.replace(old, new))


def edit_span(path, start, end, new):
    file = pathlib.Path(path)
    text = file.read_text()
    assert text.count(start) == 1 and text.count(end) == 1, (path, start, end)
    a = text.index(start)
    b = text.index(end) + len(end)
    assert a < b
    file.write_text(text[:a] + new + text[b:])


DEV = "docs/guides/development.md"

edit(
    DEV,
    "Install every package and\nevery optional extra with:\n\n" + F + "bash\nuv sync --all-extras\n" + F,
    "Install every package with its `dev` and `docs` dependency groups, which bring\n"
    "each package's optional extras, with:\n\n" + F + "bash\ntask setup\n" + F,
)

edit_span(
    DEV,
    "| Check | Command |",
    "| Combined documentation | `uv run --group docs mkdocs build --strict` |",
    "Every gate is a `task` verb, run from the repository root.\n\n"
    "| Check | Command |\n"
    "| -- | -- |\n"
    "| Install | `task setup` |\n"
    "| All tests | `task test` |\n"
    "| Lint: ruff, format check, import boundaries, Markdown and TOML formatting, dependency audit, licences | `task lint` |\n"
    "| Format in place | `task format` |\n"
    "| Strict type check | `task typecheck` |\n"
    "| Combined documentation, root and every package, strict | `task docs:build` |\n"
    "| Lint, type check, tests and documentation together | `task validate` |\n"
    "| Regenerate the derived documentation regions | `task docs:generate` |\n"
    "| Broker profile (`rn-forge-auth`, needs Docker) | see below |\n\n"
    "A narrower run has no task verb. It filters a run and is not a gate:\n"
    "`task validate` is the gate.\n\n"
    "| Run | Command |\n"
    "| -- | -- |\n"
    "| One package's tests | `uv run pytest packages/rn-forge-cli` |\n"
    "| One test by name or keyword | `uv run pytest -k test_name` |\n"
    "| Fast isolated tests (`rn-forge-django`, `rn-forge-web`) | `uv run pytest -m unit` |\n"
    "| Database-backed tests (`rn-forge-django`) | `uv run pytest -m integration` |",
)

edit(
    DEV,
    "`RN_FORGE_AUTH_KEYCLOAK_URL`. They are optional in CI (`broker-profile.yml`):\n",
    "`RN_FORGE_AUTH_KEYCLOAK_URL`. CI runs them in the `integration` job of\n"
    "`ci.yml`, against the `keycloak` service that `rn-forge-auth` declares in\n"
    "`[tool.workspace-ci.integration.keycloak]`. To run them locally:\n",
)

edit_span(
    DEV,
    "CI's `dependency-audit` job fails on a known vulnerability",
    "reason in a `#` comment beside it.",
    "`task lint` fails on a known vulnerability in `uv.lock` (`pip-audit` over\n"
    "`uv export --frozen`, [ADR-0015](../adr/ADR-0015.md)), and CI runs it in the\n"
    "`validate` job. To accept a finding, add its advisory ID and the reason to the\n"
    "`ignore` list of `[ci.checks.pip-audit]` in `.rn-forge/kiln/config.toml`, as\n"
    '`ignore = [{ id = "<ID>", reason = "<why, and when to revisit>" }]`, then run\n'
    "`task kiln:apply`. An entry without a reason is not allowed.\n\n"
    "`task lint` also fails on a dependency whose licence matches GPL, AGPL or\n"
    "`UNKNOWN`, and allows LGPL. Workspace members are left out, so the check\n"
    "covers third-party dependencies only. `[ci.checks.licenses]` in the same file\n"
    "sets `deny` and `ignore`; a dual-licensed package used under its permissive\n"
    "option goes in `ignore`, then `task kiln:apply`.",
)

edit_span(
    DEV,
    "Each package also has a standalone MkDocs site. Build it from that package's",
    "Use a temporary `--site-dir` to keep an\nexisting preview.",
    "Each package also has a standalone MkDocs site. `task docs:build` builds the root\n"
    "site and then every package's own site, each with `--strict`: the root site\n"
    "includes all ten, but a combined build does not show that each standalone site\n"
    "resolves its own links, so the task checks both. `task docs:build -- <dir>`\n"
    "writes the root site to `<dir>`, which keeps an existing preview.",
)

edit("README.md", F + "bash\nuv sync --all-extras\n" + F, F + "bash\ntask setup\n" + F)

REL = "docs/runbooks/releasing-packages.md"
edit(
    REL,
    "`.github/workflows/main.yml` names no package; the `rn-forge-devops` package\n(`uv run rn-forge-devops`) reads them from the workspace manifests\n",
    "`.github/workflows/ci.yml` names no package; `task ci:plan` reads them from the\nworkspace manifests\n",
)
edit(REL, "workflow `main.yml`, environment `pypi`", "workflow `ci.yml`, environment `pypi`")

edit(
    "packages/rn-forge-auth/docs/guides/testing.md",
    "The `broker-profile` workflow runs them weekly and on changes to this package.\nIt is not a required check and does not gate merges. The realms under\n",
    "CI runs them in the `integration` job of `ci.yml`, against the `keycloak` service\nthat this package's `pyproject.toml` declares. The realms under\n",
)

edit(
    "docs/adr/ADR-0015.md",
    "steps; [ADR-0012](ADR-0012.md) keeps their logic in `rn-forge-devops`.",
    "steps; [ADR-0012](ADR-0012.md) keeps their logic in `rn-forge-devops`.\n*Revised 2026-11-07 (F16.3):* after the kiln cutover the release job is\n`.github/workflows/_release.yml`, called by `ci.yml`.",
)
PY
# The guides, runbooks and instruction files name no `_update_board`; the
# `_structure.md` pages are managed copies (step 1), and epics, features,
# release pages and changelogs keep it as history.
absent() { local rc=0; rg -q --hidden --glob '!.git' "$@" </dev/null || rc=$?; [ "$rc" -eq 1 ]; }
absent '_update_board' CLAUDE.md README.md AGENTS.md docs/guides docs/runbooks
