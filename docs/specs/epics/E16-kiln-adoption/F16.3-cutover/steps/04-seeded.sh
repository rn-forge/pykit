#!/usr/bin/env bash
# S16.3.1 step 4: seeded.
set -euo pipefail
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
# Seeded by kiln, not in pykit or stale in pykit: take the reference's.
# pykit.code-workspace stays pykit's: VS Code rewrites it while open.
for f in .taplo.toml .mdformat.toml .yamlfmt.yaml docs/_areas.yml \
  docs/runbooks/recovering-from-drift.md docs/specs/epics/index.md; do
  mkdir -p "$(dirname "$f")"
  cp "$REF/$f" "$f"
done
