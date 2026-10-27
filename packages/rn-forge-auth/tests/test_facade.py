"""The auth facade must not load the OIDC adapter."""

from __future__ import annotations

import subprocess
import sys

SCRIPT = """
import sys
import rn_forge.auth
offenders = [n for n in ("rn_forge.auth.oidc", "jwt") if n in sys.modules]
print("\\n".join(offenders))
"""


def test_facade_imports_no_oidc() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"loaded by the facade: {result.stdout}"
