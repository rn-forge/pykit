#!/usr/bin/env bash
# S16.3.1 step 1: managed.
set -euo pipefail
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
# Every `managed` entry of the reference's state.json except mkdocs.yml's nav,
# which docs:generate re-derives (step 13).
python3 -I - "$REF" <<'PY'
import json, pathlib, shutil, sys
ref = pathlib.Path(sys.argv[1])
entries = json.loads((ref / ".rn-forge/kiln/state.json").read_text())["entries"]
managed = sorted(p for p, e in entries.items() if e["kind"] == "managed")
assert len(managed) == 28, len(managed)
for p in managed:
    dst = pathlib.Path(p)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ref / p, dst)
    print("copied", p)
PY
cp "$REF/.rn-forge/kiln/state.json" .rn-forge/kiln/state.json
cp "$REF/.rn-forge/kiln/config.toml" .rn-forge/kiln/config.toml
