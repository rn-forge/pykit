"""The auth facade must not load the adapters."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import rn_forge.auth

SCRIPT = """
import sys
import rn_forge.auth
offenders = [n for n in ("rn_forge.auth.oidc", "rn_forge.auth.redis", "jwt") if n in sys.modules]
print("\\n".join(offenders))
"""


def test_facade_imports_no_adapter_modules() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"loaded by the facade: {result.stdout}"


def test_core_modules_import_only_stdlib_and_rn_forge() -> None:
    """Third-party libraries load only through rn_forge.web and commons."""
    core = Path(rn_forge.auth.__file__).parent
    offenders: dict[str, set[str]] = {}
    for path in core.glob("*.py"):
        if path.stem in {"oidc", "redis"}:
            continue
        tree = ast.parse(path.read_text())
        roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
        }
        foreign = roots - set(sys.stdlib_module_names) - {"rn_forge"}
        if foreign:
            offenders[path.name] = foreign
    assert offenders == {}


def test_facade_imports_no_adapter_libraries() -> None:
    script = (
        "import sys, rn_forge.auth;"
        "print([n for n in ('jwt', 'authlib', 'redis') if n in sys.modules])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
