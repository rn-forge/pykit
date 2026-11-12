#!/usr/bin/env bash
# S16.3.1 step 8: member mkdocs.
set -euo pipefail
# Members' mkdocs.yml: no `site_dir`. `task docs:build` builds each member into
# a temporary directory, and a bare `mkdocs build` writes the default `site/`.
for f in packages/rn-forge-*/mkdocs.yml; do
  test "$(grep -c '^site_dir: \.out/site$' "$f")" = 1
  sed -i.bak '/^site_dir: \.out\/site$/d' "$f"
  rm "$f.bak"
done
