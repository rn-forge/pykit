#!/usr/bin/env bash
# S16.3.11: format pykit's own files with kiln's formatters and write the result as a patch.
# Usage, from the repository root: bash <this file> <patch-path>
# Overlays steps 01 to 04, formats, and stops. It resets and cleans nothing.
set -euo pipefail
PATCH="${1:?usage: format.sh <patch-path>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

test "$(git branch --show-current)" = feature/kiln-cutover
test -z "$(git status --porcelain)"

for step in 01-managed 02-config 03-blocks 04-seeded; do
  bash "$HERE/steps/$step.sh" >/dev/null
done
git status --porcelain >"$PATCH.overlay"
task setup
# The root pyproject gains google-yamlfmt only in step 6, and the next `task setup` removes it.
uv pip install google-yamlfmt==0.21.0
task format

# A changed tracked path is listed by name in the overlay; a collapsed
# untracked directory holds no tracked path.
sed 's/^...//' "$PATCH.overlay" >"$PATCH.overlay-paths"
paths=()
while IFS= read -r path; do
  paths+=("$path")
done < <(git diff --name-only -- '*.md' '*.toml' '*.yml' '*.yaml' | grep -vxF -f "$PATCH.overlay-paths" || true)
rm "$PATCH.overlay-paths"
test "${#paths[@]}" -gt 0 || { echo "no formatting-only change" >&2; exit 1; }

git diff -- "${paths[@]}" >"$PATCH"
printf '%s\n' "${paths[@]}"
echo "${#paths[@]} files in $PATCH; overlay paths in $PATCH.overlay"
