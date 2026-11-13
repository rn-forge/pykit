#!/usr/bin/env bash
# Build the reference repository for S16.3.1 from pykit-new.toml and pykit-deps.sh.
# Usage: build-reference.sh   (REF and KILN override the default paths)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd "$HERE/../../../../../.." && pwd)"
KILN="${KILN:-$WS/kiln}"
REF="${REF:-$WS/_reference/pykit}"

# The caller deletes both, so nothing here removes a directory.
test ! -e "$REF" || { echo "remove $REF first" >&2; exit 1; }
test ! -e "$KILN/.staging/pykit" || { echo "remove $KILN/.staging/pykit first" >&2; exit 1; }
test "$(git -C "$KILN" branch --show-current)" = feature/v1 || { echo "kiln is not on feature/v1" >&2; exit 1; }
test -z "$(git -C "$KILN" status --porcelain --untracked-files=no)" || { echo "kiln has uncommitted changes" >&2; exit 1; }
echo "kiln at $(git -C "$KILN" rev-parse --short HEAD)"

(cd "$KILN" && uv run kiln new "$REF" --archetype python-lib --docs mkdocs \
  --owner rn-forge --config "$HERE/pykit-new.toml" --yes)
cd "$REF"
bash "$HERE/pykit-deps.sh"
task setup
# Expected to fail at python:lint:imports only: the "own" contracts need pykit's code.
task validate
