#!/usr/bin/env bash
# S16.3.1 step 7: member pyproject.
set -euo pipefail
# Each member's uv_build pin, [tool.pyright] table and source-exclude, as the
# reference's members have them, plus one pykit line (reportUnnecessaryTypeIgnoreComment).
python3 -I - <<'PY'
import pathlib

PIN_OLD = 'requires = ["uv_build>=0.11.28,<0.12.0"]'
PIN_NEW = 'requires = ["uv_build>=0.13.7,<0.14.0"]'
BUILD = 'build-backend = "uv_build"\n'
PYRIGHT = (
    "\n[tool.pyright]\n"
    'typeCheckingMode = "strict"\n'
    "reportMissingTypeStubs = false\n"
    'reportUnnecessaryTypeIgnoreComment = "error"\n'
    'venv = ".venv"\n'
    'venvPath = "../.."\n'
)
paths = sorted(pathlib.Path("packages").glob("rn-forge-*/pyproject.toml"))
assert len(paths) == 10, paths
for p in paths:
    t = p.read_text()
    assert t.count(PIN_OLD) == 1 and t.count(BUILD) == 1, p
    assert "[tool.pyright]" not in t and "source-exclude" not in t, p
    t = t.replace(PIN_OLD, PIN_NEW).replace(BUILD, BUILD + PYRIGHT)
    out, seen = [], False
    for line in t.splitlines(keepends=True):
        out.append(line)
        if line.startswith("module-name = "):
            assert not seen, p
            seen = True
            out.append('source-exclude = ["**/.DS_Store"]\n')
    assert seen, p
    p.write_text("".join(out))
PY
