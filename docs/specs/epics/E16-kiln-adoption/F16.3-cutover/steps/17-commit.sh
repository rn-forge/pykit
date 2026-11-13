#!/usr/bin/env bash
# S16.3.1 step 17: commit.
set -euo pipefail
test "$(git rev-parse HEAD)" = "${BASE:?set BASE to the commit step 0 printed}"
git add -- docs mkdocs.yml README.md 'packages/*/docs/*' 'packages/*/mkdocs.yml' \
  'packages/*/README.md' 'packages/*/CHANGELOG.md'
git commit -m "S16.3.1 docs"
git add -- .rn-forge tasks Taskfile.yml .github/actions .github/dependabot.yml \
  '.github/workflows/_*.yml' .github/workflows/ci.yml .github/workflows/scorecard.yml \
  sonar-project.properties .editorconfig .mdformat.toml \
  .taplo.toml .yamlfmt.yaml .gitignore .importlinter AGENTS.md
git commit -m "S16.3.1 kiln"
git add -- .github/workflows/main.yml .github/workflows/internal-ranges.yml \
  .github/workflows/umbrella-release.yml .github/workflows/broker-profile.yml src
git commit -m "S16.3.1 legacy"
git add -- pyproject.toml 'packages/*/pyproject.toml' uv.lock
git commit -m "S16.3.1 pyproject"
# Anything left is formatting of a non-Markdown file: add it by its listed paths.
git status --porcelain
