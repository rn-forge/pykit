"""The commons facade imports eagerly, so it must not load the optional modules."""

from __future__ import annotations

import subprocess
import sys

FORBIDDEN = (
    "rn_forge.commons.generation",
    "rn_forge.commons.text.templates",
    "rn_forge.commons.text.markdown",
    "jinja2",
    "markdown",
    "markdown_it",
)

SCRIPT = f"""
import sys
import rn_forge.commons
from rn_forge.commons.findings import Finding
forbidden = {FORBIDDEN!r}
offenders = sorted(
    name for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in forbidden)
)
print("\\n".join(offenders))
"""


def test_facade_imports_no_extras() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"loaded by the facade: {result.stdout}"
