"""The uv workspace adapter: manifest reading and the `smoke` check.

Members are those of the root `[tool.uv.workspace]`. A member's internal
requirements are the members named in its dependencies, optional dependencies and
dependency groups. CI settings live in `[tool.workspace-ci]` tables: the root one
holds workspace-wide settings, a member's own holds that member's extra checks.
"""

from __future__ import annotations

import fnmatch
import subprocess
import tempfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from rn_forge.devops.ci import (
    Package,
    Smoke,
    Workspace,
    normalize,
    requirement_name,
)

TOOL = "workspace-ci"

IMPORT_SNIPPET = """
import importlib, runpy, sys
setup, *modules = sys.argv[1:]
if setup:
    runpy.run_path(setup)
for name in modules:
    importlib.import_module(name)
    print("imported", name)
"""


def find_root(start: Path) -> Path:
    """Return the nearest directory at or above `start` whose `pyproject.toml`
    declares `[tool.uv.workspace]`.

    Raises:
        FileNotFoundError: When there is none.
    """
    for directory in (start, *start.parents):
        manifest = directory / "pyproject.toml"
        if manifest.is_file() and "workspace" in tomllib.loads(
            manifest.read_text()
        ).get("tool", {}).get("uv", {}):
            return directory
    raise FileNotFoundError(f"no uv workspace at or above {start}")


def load_workspace(root: Path) -> Workspace:
    """Read the uv workspace at `root` into the core's graph."""
    manifest: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text())
    workspace = manifest["tool"]["uv"]["workspace"]
    excluded = workspace.get("exclude", [])
    dirs = sorted(
        {
            path.parent
            for pattern in workspace["members"]
            for path in root.glob(f"{pattern}/pyproject.toml")
            if not any(
                fnmatch.fnmatch(path.parent.relative_to(root).as_posix(), x)
                for x in excluded
            )
        }
    )
    manifests = {
        path: tomllib.loads((path / "pyproject.toml").read_text()) for path in dirs
    }
    names = {normalize(m["project"]["name"]) for m in manifests.values()}
    packages: dict[str, Package] = {}
    for path, member in manifests.items():
        project = member["project"]
        tool = member.get("tool", {})
        requirements: list[str] = list(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            requirements += extra
        for group in member.get("dependency-groups", {}).values():
            requirements += [item for item in group if isinstance(item, str)]
        name = normalize(project["name"])
        ci = tool.get(TOOL, {})
        smoke = ci.get("smoke")
        packages[name] = Package(
            name=name,
            dir=path.relative_to(root).as_posix(),
            module=tool.get("uv", {}).get("build-backend", {}).get("module-name")
            or name.replace("-", "_"),
            requires={r for r in map(requirement_name, requirements) if r in names}
            - {name},
            postgres_env=ci["postgres"]["env"] if "postgres" in ci else None,
            smoke=(
                Smoke(
                    modules=smoke.get("modules", []),
                    extras=smoke.get("extras", {}),
                    setup=smoke.get("setup", ""),
                )
                if smoke is not None
                else None
            ),
        )
    settings = manifest.get("tool", {}).get(TOOL, {})
    return Workspace(
        root=root,
        packages=packages,
        pytest_args=settings.get("pytest-args", []),
        suites=settings.get("suites", {}),
    )


def smoke(workspace: Workspace, package_name: str, extra: str) -> int:
    """Install `package_name` with only `extra` from wheels built from this checkout
    into a clean venv, then import the modules its `[tool.workspace-ci.smoke]` lists.

    The install uses exactly what the wheels declare, so an extra that omits a
    dependency another extra brings fails here. An empty `extra` installs the
    package with no extra.

    Returns:
        The exit status of the import step.
    """
    root, packages = workspace.root, workspace.packages
    package = packages[normalize(package_name)]
    config = package.smoke
    assert config is not None
    modules = [*config.modules, *(config.extras[extra] if extra else [])]

    def closure(name: str, seen: set[str]) -> set[str]:
        for requirement in packages[name].requires - seen:
            seen.add(requirement)
            closure(requirement, seen)
        return seen

    def requires(wheel: Path) -> list[Requirement]:
        with zipfile.ZipFile(wheel) as archive:
            name = next(
                n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(name).decode())
        return [Requirement(line) for line in metadata.get_all("Requires-Dist") or []]

    def active(req: Requirement, extras: set[str]) -> bool:
        return req.marker is None or any(
            req.marker.evaluate({"extra": e}) for e in ("", *extras)
        )

    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        for name in sorted(closure(package.name, {package.name})):
            subprocess.run(
                [
                    "uv",
                    "build",
                    "-q",
                    "--package",
                    name,
                    "--wheel",
                    "--out-dir",
                    str(dist),
                ],
                cwd=root,
                check=True,
            )
        wheels = {normalize(w.name.split("-")[0]): w for w in dist.glob("*.whl")}

        # Walk the wheels' own metadata: which extras each local wheel is asked
        # for, and every external requirement those extras bring.
        local: dict[str, set[str]] = {}
        pending: list[tuple[str, set[str]]] = [
            (package.name, {extra} if extra else set())
        ]
        while pending:
            name, extras = pending.pop()
            if name in local and extras <= local[name]:
                continue
            local[name] = local.get(name, set()) | extras
            pending += [
                (normalize(req.name), set(req.extras))
                for req in requires(wheels[name])
                if normalize(req.name) in wheels
                and normalize(req.name) != name
                and active(req, local[name])
            ]
        external: set[str] = set()
        for name, extras in local.items():
            for req in requires(wheels[name]):
                if normalize(req.name) not in wheels and active(req, extras):
                    req.marker = None
                    external.add(str(req))
        print(f"extra={extra or '(none)'} local={local}")

        venv = Path(tmp) / "venv"
        python = venv / "bin" / "python"
        subprocess.run(["uv", "venv", "-q", str(venv)], cwd=root, check=True)
        install = ["uv", "pip", "install", "-q", "--python", str(python)]
        # Local wheels go in without deps, so their git-pinned siblings are never
        # fetched; everything else they declare is in `external`.
        if external:
            subprocess.run([*install, *sorted(external)], check=True)
        subprocess.run(
            [*install, "--no-deps", *(str(wheels[n]) for n in local)], check=True
        )
        setup = str(root / package.dir / config.setup) if config.setup else ""
        return subprocess.run(
            [str(python), "-c", IMPORT_SNIPPET, setup, *modules], check=False
        ).returncode
