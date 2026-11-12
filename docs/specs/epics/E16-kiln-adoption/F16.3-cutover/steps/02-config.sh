#!/usr/bin/env bash
# S16.3.1 step 2: config.
set -euo pipefail
absent() { local rc=0; rg -q --hidden --glob '!.git' "$@" </dev/null || rc=$?; [ "$rc" -eq 1 ]; }
absent '^\[source\]' .rn-forge/kiln/config.toml
grep -qx 'archetype = "python-lib"' .rn-forge/kiln/config.toml
grep -qx 'release = "pypi"' .rn-forge/kiln/config.toml
grep -qx 'import_contracts = "own"' .rn-forge/kiln/config.toml
grep -qx 'umbrella-release = true' .rn-forge/kiln/config.toml
grep -qx 'scorecard = true' .rn-forge/kiln/config.toml
grep -qx 'ref = "feature/v1"' .rn-forge/kiln/config.toml
