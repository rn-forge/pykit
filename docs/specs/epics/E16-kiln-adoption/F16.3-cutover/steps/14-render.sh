#!/usr/bin/env bash
# S16.3.1 step 14: render.
set -euo pipefail
task kiln:diff
# exit 0, no output after the command line
task kiln:apply
# exit 0
