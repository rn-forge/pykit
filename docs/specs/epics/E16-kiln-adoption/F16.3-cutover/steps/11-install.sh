#!/usr/bin/env bash
# S16.3.1 step 11: install.
set -euo pipefail
cp uv.lock /tmp/pykit-uv.lock.before
task setup
diff -u /tmp/pykit-uv.lock.before uv.lock > /tmp/pykit-uv.lock.diff || true
# No locked version of an existing package moves; the diff adds the task tools
# (actionlint-py, pip-audit, taplo, zizmor and their dependencies) and turns the
# root package's `editable` into `virtual`.
if grep -E '^-version = ' /tmp/pykit-uv.lock.diff; then echo "a locked version moved"; exit 1; fi
grep -c '^+name = ' /tmp/pykit-uv.lock.diff
grep -E '^[-+]source = \{ (editable|virtual)' /tmp/pykit-uv.lock.diff
