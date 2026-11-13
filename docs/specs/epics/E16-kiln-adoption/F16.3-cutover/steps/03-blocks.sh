#!/usr/bin/env bash
# S16.3.1 step 3: blocks.
set -euo pipefail
REF="${REF:-/Users/rohitnarayanan/Devel/workspaces/rn-forge/_reference/pykit}"
python3 -I - "$REF" <<'PY'
import pathlib
import re
import shutil
import sys

ref = pathlib.Path(sys.argv[1])


def block(text, begin, end):
    a = text.index(begin)
    b = text.index(end) + len(end)
    assert text.count(begin) == 1 and text.count(end) == 1 and a < b
    return text[a:b]


# AGENTS.md: the block goes after pykit's last line, nothing else changes.
agents = pathlib.Path("AGENTS.md")
b = block((ref / "AGENTS.md").read_text(), "<!-- BEGIN rn-forge kiln -->", "<!-- END rn-forge kiln -->")
text = agents.read_text()
assert "BEGIN rn-forge kiln" not in text
agents.write_text(text.rstrip("\n") + "\n\n" + b + "\n")

# .importlinter: the block goes first; pykit's own contracts stay below it, but
# pykit's [importlinter] section (root_packages, include_external_packages) is
# the block's now and goes.
il = pathlib.Path(".importlinter")
b = block((ref / ".importlinter").read_text(), "# BEGIN rn-forge kiln", "# END rn-forge kiln")
text = il.read_text()
text, n = re.subn(r"\[importlinter\]\nroot_packages =\n(?:    [^\n]+\n)+include_external_packages = True\n\n", "", text)
assert n == 1
il.write_text(b + "\n\n" + text)

# .gitignore: the reference's file is the header plus the block, and replaces
# pykit's. pykit's .DS_Store, cache and coverage lines are in the block; the
# members' `site_dir` writes no `.out` any more (step 8) and the sonar-cleanup
# skill writes under .git/ (kiln S16.7.5). One line stays, after the block:
# rn_forge.commons.testing's output root, which commons' own tests write.
shutil.copyfile(ref / ".gitignore", ".gitignore")
with open(".gitignore", "a") as handle:
    handle.write("\n# rn_forge.commons.testing output root\n.out/\n")
PY
