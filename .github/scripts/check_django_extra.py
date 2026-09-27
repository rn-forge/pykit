"""Install the built rn-forge-django wheel with ONE extra into a clean venv and import it.

CI syncs ``--all-extras``, so an extra that forgets a dependency another extra
happens to bring is invisible there. This installs exactly what the wheel's own
``Requires-Dist`` declares for the chosen extra, then imports that extra's modules.

The sibling rn-forge wheels are pinned in the metadata as git tags; they are
swapped for the wheels built from this checkout, keeping the extras each
requirement asks for — so a missing ``[excel]`` still goes missing.

Usage (from the repo root, after ``uv build --wheel`` of commons, web and django
into ``dist/``)::

    uv run --no-project --with packaging python .github/scripts/check_django_extra.py oidc
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path

from packaging.requirements import Requirement

BASE = "base"
MODULES: dict[str, list[str]] = {
    BASE: ["rn_forge.django", "rn_forge.django.models"],
    "drf": [
        "rn_forge.django.drf",
        "rn_forge.django.drf.views",
        "rn_forge.django.auth.drf",
    ],
    "fixtures": ["rn_forge.django.fixtures"],
    "jwt": ["rn_forge.django.auth.jwt"],
    "oidc": ["rn_forge.django.auth.drf.oidc"],
    "celery": ["rn_forge.django.celery"],
    "openapi": ["rn_forge.django.drf.openapi"],
    "saml": ["rn_forge.django.auth.saml"],
}

IMPORT_SNIPPET = """
import importlib, sys
import django
from django.conf import settings
settings.configure(
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
django.setup()
for name in sys.argv[1:]:
    importlib.import_module(name)
    print("imported", name)
"""


def _requires(wheel: Path) -> list[Requirement]:
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(name).decode())
    return [Requirement(line) for line in metadata.get_all("Requires-Dist") or []]


def _active(req: Requirement, extras: set[str]) -> bool:
    if req.marker is None:
        return True
    return any(req.marker.evaluate({"extra": e}) for e in ("", *extras))


def _resolve(
    wheels: dict[str, Path], extra: str
) -> tuple[dict[str, set[str]], set[str]]:
    """Extras requested of each local wheel, and every external requirement, per the metadata."""
    local: dict[str, set[str]] = {}
    pending: list[tuple[str, set[str]]] = [
        ("rn-forge-django", set() if extra == BASE else {extra})
    ]
    while pending:
        name, extras = pending.pop()
        if name in local and extras <= local[name]:
            continue
        local[name] = local.get(name, set()) | extras
        pending.extend(
            (req.name, set(req.extras))
            for req in _requires(wheels[name])
            if req.name in wheels and req.name != name and _active(req, local[name])
        )
    external: set[str] = set()
    for name, extras in local.items():
        for req in _requires(wheels[name]):
            if req.name not in wheels and _active(req, extras):
                req.marker = None
                external.add(str(req))
    return local, external


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("extra", choices=sorted(MODULES))
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    extra: str = args.extra
    wheels = {
        wheel.name.split("-")[0].replace("_", "-"): wheel
        for wheel in args.dist.resolve().glob("rn_forge_*.whl")
    }
    local, external = _resolve(wheels, extra)
    print(f"extra={extra} local={local}")

    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp) / "venv"
        python = venv / "bin" / "python"
        subprocess.run(["uv", "venv", "-q", "-p", "3.14", str(venv)], check=True)
        install = ["uv", "pip", "install", "-q", "--python", str(python)]
        # Local wheels go in without deps, so their git-pinned siblings are never
        # fetched; everything else they declare is in `external`.
        subprocess.run([*install, *sorted(external)], check=True)
        subprocess.run(
            [*install, "--no-deps", *(str(wheels[n]) for n in local)], check=True
        )
        modules = [*MODULES[BASE], *(MODULES[extra] if extra != BASE else [])]
        return subprocess.run([str(python), "-c", IMPORT_SNIPPET, *modules]).returncode


if __name__ == "__main__":
    sys.exit(main())
