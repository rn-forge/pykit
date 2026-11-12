#!/usr/bin/env bash
# S16.3.1 step 15: gates.
set -euo pipefail
task validate                      # exit 0; about 7 minutes
KILN_DOCTOR_FULL=1 task lint       # exit 0
