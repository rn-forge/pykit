#!/usr/bin/env bash
# S16.3.1 step 0: preconditions.
set -euo pipefail
test "$(basename "$PWD")" = pykit
test "$(git remote get-url origin | sed 's/\.git$//')" = https://github.com/rn-forge/pykit
test "$(git branch --show-current)" = feature/kiln-cutover
test "$(git log --format=%s | grep -cx S16.3.11)" -ge 1
test "$(git log --format=%s | grep -cx S16.3.12)" -ge 1
test -z "$(git status --porcelain)"
test ! -e .rn-forge/kiln
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
test "$(git -C "$REF" rev-parse --short HEAD)" = c9cc5da
test -z "$(git -C "$REF" status --porcelain)"
grep -qx 'ref = "feature/v1"' "$REF/.rn-forge/kiln/config.toml"
git ls-remote --exit-code https://github.com/rn-forge/kiln refs/heads/feature/v1 >/dev/null
git rev-parse HEAD   # BASE: write it down
