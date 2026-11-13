#!/usr/bin/env bash
# S16.3.1 step 16: acceptance.
set -euo pipefail
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
absent() { local rc=0; rg -q --hidden --glob '!.git' "$@" </dev/null || rc=$?; [ "$rc" -eq 1 ]; }
# step 5: the four legacy workflows and the root package are gone
for f in main internal-ranges umbrella-release broker-profile docs; do test ! -e ".github/workflows/$f.yml"; done
for f in ci _docs _integration _release _smoke _sonar _verify-release scorecard; do test -f ".github/workflows/$f.yml"; done
test ! -e src
test ! -e docs/_update_board.sh
test -f .yamlfmt.yaml   # step 4
# S16.3.12: pykit's board and scope fences are kiln's
absent 'board:start|scope:start' docs/specs/index.md docs/releases/release-*/index.md
grep -qx '<!-- BEGIN derived board -->' docs/specs/index.md
# step 1: every managed file but mkdocs.yml is the reference's, byte for byte
python3 -I - "$REF" <<'PY'
import filecmp, json, pathlib, sys
ref = pathlib.Path(sys.argv[1])
entries = json.loads((ref / ".rn-forge/kiln/state.json").read_text())["entries"]
managed = sorted(p for p, e in entries.items() if e["kind"] == "managed" and p != "mkdocs.yml")
assert len(managed) == 27, len(managed)
bad = [p for p in managed if not filecmp.cmp(ref / p, p, shallow=False)]
assert not bad, bad
PY
# step 3: the three managed blocks are the reference's, byte for byte
python3 -I - "$REF" <<'PY'
import pathlib, sys
ref = pathlib.Path(sys.argv[1])
for path, begin, end in [
    ("AGENTS.md", "<!-- BEGIN rn-forge kiln -->", "<!-- END rn-forge kiln -->"),
    (".importlinter", "# BEGIN rn-forge kiln", "# END rn-forge kiln"),
    (".gitignore", "# BEGIN rn-forge kiln", "# END rn-forge kiln"),
]:
    def cut(t):
        return t[t.index(begin):t.index(end) + len(end)]
    assert cut((ref / path).read_text()) == cut(pathlib.Path(path).read_text()), path
PY
test "$(git diff --numstat -- AGENTS.md)" = "$(printf '31\t0\tAGENTS.md')"
diff <(cat "$REF/.gitignore"; printf '\n# rn_forge.commons.testing output root\n.out/\n') .gitignore
# step 2: no [source]; the pin is kiln's branch until the tag
absent '^\[source\]' .rn-forge/kiln/config.toml
grep -qx 'ref = "feature/v1"' .rn-forge/kiln/config.toml
# step 9: the old service tables are gone, the integration tables are in
absent '^\[tool\.workspace-ci\.(postgres|redis)\]' packages
grep -qx '\[tool.workspace-ci.integration.postgres\]' packages/rn-forge-sqlalchemy/pyproject.toml
grep -qx '\[tool.workspace-ci.integration.postgres\]' packages/rn-forge-django/pyproject.toml
grep -qx '\[tool.workspace-ci.integration.redis\]' packages/rn-forge-auth/pyproject.toml
grep -qx '\[tool.workspace-ci.integration.keycloak\]' packages/rn-forge-auth/pyproject.toml
# step 10: no document names a removed workflow, and no gate runs through uv
absent '_update_board' CLAUDE.md README.md AGENTS.md docs/guides docs/runbooks docs/_structure.md docs/specs/_structure.md
absent 'broker-profile|main\.yml|internal-ranges\.yml|umbrella-release\.yml' docs/guides docs/runbooks packages/rn-forge-auth/docs
absent 'uv run (ruff|pyright|lint-imports|mkdocs|--group)|uv sync' CLAUDE.md README.md docs/guides/development.md docs/runbooks
# step 6: the root pyproject differs from the reference's only by pykit's nuances
python3 -I - "$REF/pyproject.toml" pyproject.toml <<'PY' | diff - <(cat <<'EOF'
dependency-groups.dev
dependency-groups.docs
dependency-groups.workspace
project.authors
project.description
project.readme
tool.pyright.ignore
tool.pyright.reportUnnecessaryTypeIgnoreComment
tool.pytest.ini_options.markers
tool.ruff.lint.extend-select
tool.ruff.lint.flake8-bugbear.extend-immutable-calls
tool.ruff.lint.isort.known-third-party
tool.ruff.lint.per-file-ignores.**/tests/*
tool.ruff.lint.per-file-ignores..github/scripts/*
tool.ruff.lint.per-file-ignores.conftest.py
tool.workspace-ci.suites.scaffold
EOF
)
import sys, tomllib
def flat(d, p=""):
    for k, v in d.items():
        q = f"{p}.{k}" if p else k
        if isinstance(v, dict):
            yield from flat(v, q)
        else:
            yield q, v
a, b = (dict(flat(tomllib.load(open(f, "rb")))) for f in sys.argv[1:3])
for k in sorted(set(a) | set(b)):
    if a.get(k, "<absent>") != b.get(k, "<absent>"):
        print(k)
PY
# step 6: a blank line before every table, and [tool.pyright] keys sorted
python3 -I - <<'PY'
import re, tomllib
text = open("pyproject.toml").read()
assert not re.search(r"[^\n]\n\[", text)
keys = list(tomllib.loads(text)["tool"]["pyright"])
assert keys == sorted(keys), keys
PY
# steps 7 and 8: every member has the reference's build pin, pyright table and
# source-exclude, and no site_dir
python3 -I - <<'PY'
import pathlib, tomllib
paths = sorted(pathlib.Path("packages").glob("rn-forge-*/pyproject.toml"))
assert len(paths) == 10
for p in paths:
    d = tomllib.loads(p.read_text())
    assert d["build-system"]["requires"] == ["uv_build>=0.13.7,<0.14.0"], p
    assert d["tool"]["pyright"] == {
        "typeCheckingMode": "strict", "reportMissingTypeStubs": False,
        "reportUnnecessaryTypeIgnoreComment": "error",
        "venv": ".venv", "venvPath": "../..",
    }, p
    assert d["tool"]["uv"]["build-backend"]["source-exclude"] == ["**/.DS_Store"], p
    assert "site_dir" not in p.with_name("mkdocs.yml").read_text(), p
PY
# nothing under any package's src/ or tests/ changed, and nothing is staged
if git diff --name-only | rg -q '/(src|tests)/|conftest'; then exit 1; fi
git diff --cached --quiet
# the tracked files that are not Markdown: exactly this list
diff <(git diff --name-only | rg -v '\.md$' | LC_ALL=C sort) - <<'EOF'
.editorconfig
.github/actions/setup/action.yml
.github/dependabot.yml
.github/workflows/broker-profile.yml
.github/workflows/internal-ranges.yml
.github/workflows/main.yml
.github/workflows/scorecard.yml
.github/workflows/umbrella-release.yml
.gitignore
.importlinter
.mdformat.toml
docs/_areas.yml
docs/_update_board.sh
mkdocs.yml
packages/rn-forge-auth/mkdocs.yml
packages/rn-forge-auth/pyproject.toml
packages/rn-forge-cli/mkdocs.yml
packages/rn-forge-cli/pyproject.toml
packages/rn-forge-commons/mkdocs.yml
packages/rn-forge-commons/pyproject.toml
packages/rn-forge-data/mkdocs.yml
packages/rn-forge-data/pyproject.toml
packages/rn-forge-devops/mkdocs.yml
packages/rn-forge-devops/pyproject.toml
packages/rn-forge-django/mkdocs.yml
packages/rn-forge-django/pyproject.toml
packages/rn-forge-fastapi/mkdocs.yml
packages/rn-forge-fastapi/pyproject.toml
packages/rn-forge-sqlalchemy/mkdocs.yml
packages/rn-forge-sqlalchemy/pyproject.toml
packages/rn-forge-tooling/mkdocs.yml
packages/rn-forge-tooling/pyproject.toml
packages/rn-forge-web/mkdocs.yml
packages/rn-forge-web/pyproject.toml
pyproject.toml
sonar-project.properties
src/pykit/__init__.py
uv.lock
EOF
# the untracked files: exactly kiln's
diff <(git status --short | rg '^\?\?' | LC_ALL=C sort) - <<'EOF'
?? .github/workflows/_docs.yml
?? .github/workflows/_integration.yml
?? .github/workflows/_release.yml
?? .github/workflows/_smoke.yml
?? .github/workflows/_sonar.yml
?? .github/workflows/_verify-release.yml
?? .github/workflows/ci.yml
?? .rn-forge/
?? .taplo.toml
?? .yamlfmt.yaml
?? Taskfile.yml
?? docs/runbooks/recovering-from-drift.md
?? docs/specs/epics/index.md
?? tasks/
EOF
