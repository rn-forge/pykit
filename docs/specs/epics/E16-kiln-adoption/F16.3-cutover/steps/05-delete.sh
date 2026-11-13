#!/usr/bin/env bash
# S16.3.1 step 5: delete.
set -euo pipefail
# The four legacy workflows (kiln's ci.yml, derived checks and the keycloak
# integration service replace them), the root package and the board script
# (kiln's `task docs:generate` writes the derived regions it wrote).
rm .github/workflows/main.yml .github/workflows/internal-ranges.yml \
  .github/workflows/umbrella-release.yml .github/workflows/broker-profile.yml
rm -r src
rm docs/_update_board.sh
# `.out` is untracked build output of the members' old `site_dir` (step 7).
for d in .out packages/rn-forge-*/.out; do
  if [ -e "$d" ]; then rm -r "$d"; fi
done
test ! -e .github/workflows/main.yml
test ! -e src
test ! -e docs/_update_board.sh
