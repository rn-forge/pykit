"""Plan and run the workspace CI pipeline from the uv workspace's own manifests.

Packages are the members of the root `[tool.uv.workspace]`. A package's internal
requirements are the members named in its dependencies, optional dependencies and
dependency groups. CI settings live in `[tool.workspace-ci]` tables: the root one
holds workspace-wide settings, a package's own holds that package's extra checks.
The release runbook describes the pipeline.

Usage:
    workspace_ci.py plan [BASE_REF]          `$GITHUB_OUTPUT` lines for the run
    workspace_ci.py releasable OK_DIR NAME...  the NAMEs whose checks all passed
    workspace_ci.py released                 `name dir module version` per tag at HEAD
    workspace_ci.py smoke PACKAGE [EXTRA]    install one extra from built wheels and import it
"""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass, field
from email.parser import Parser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOL = "workspace-ci"
# Changes under these paths select no package.
UNSCOPED = ("docs/",)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    return normalize(re.split(r"[\s\[<>=!~;@]", requirement.strip(), maxsplit=1)[0])


@dataclass
class Package:
    name: str
    dir: str
    module: str
    requires: set[str] = field(default_factory=set)
    ci: dict[str, Any] = field(default_factory=dict)

    def checks(self) -> list[dict[str, str]]:
        """Every check that must pass before this package may be released."""
        checks = [{"kind": "verify", "marker": f"{self.name}.verify"}]
        if "postgres" in self.ci:
            checks.append({"kind": "postgres", "marker": f"{self.name}.postgres"})
        if "smoke" in self.ci:
            checks.append(
                {"kind": "smoke", "extra": "", "marker": f"{self.name}.smoke"}
            )
            checks += [
                {
                    "kind": "smoke",
                    "extra": extra,
                    "marker": f"{self.name}.smoke-{extra}",
                }
                for extra in self.ci["smoke"].get("extras", {})
            ]
        return checks


def root_manifest() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def load_packages() -> dict[str, Package]:
    workspace = root_manifest()["tool"]["uv"]["workspace"]
    excluded = workspace.get("exclude", [])
    dirs = sorted(
        {
            path.parent
            for pattern in workspace["members"]
            for path in ROOT.glob(f"{pattern}/pyproject.toml")
            if not any(
                fnmatch.fnmatch(path.parent.relative_to(ROOT).as_posix(), x)
                for x in excluded
            )
        }
    )
    manifests = {
        path: tomllib.loads((path / "pyproject.toml").read_text()) for path in dirs
    }
    names = {normalize(m["project"]["name"]) for m in manifests.values()}
    packages: dict[str, Package] = {}
    for path, manifest in manifests.items():
        project = manifest["project"]
        tool = manifest.get("tool", {})
        requirements: list[str] = list(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            requirements += extra
        for group in manifest.get("dependency-groups", {}).values():
            requirements += [item for item in group if isinstance(item, str)]
        name = normalize(project["name"])
        packages[name] = Package(
            name=name,
            dir=path.relative_to(ROOT).as_posix(),
            module=tool.get("uv", {}).get("build-backend", {}).get("module-name")
            or name.replace("-", "_"),
            requires={r for r in map(requirement_name, requirements) if r in names}
            - {name},
            ci=tool.get(TOOL, {}),
        )
    return packages


def release_order(packages: dict[str, Package], names: set[str]) -> list[str]:
    """`names` with every package after its internal requirements."""
    order: list[str] = []
    pending = sorted(names)
    while pending:
        ready = [n for n in pending if not (packages[n].requires & names) - set(order)]
        order += ready
        pending = [n for n in pending if n not in ready]
    return order


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out.splitlines()


def select(packages: dict[str, Package], base: str) -> set[str]:
    """Packages with changed files, plus every package that depends on one.

    An empty base, or a change outside every package and `UNSCOPED`, selects all.
    """
    if not base:
        return set(packages)
    selected: set[str] = set()
    for file in changed_files(base):
        owner = next(
            (p.name for p in packages.values() if file.startswith(f"{p.dir}/")), None
        )
        if owner:
            selected.add(owner)
        elif not file.startswith(UNSCOPED):
            return set(packages)
    grew = True
    while grew:
        grew = False
        for package in packages.values():
            if package.name not in selected and package.requires & selected:
                selected.add(package.name)
                grew = True
    return selected


def plan(base: str) -> None:
    packages = load_packages()
    settings = root_manifest().get("tool", {}).get(TOOL, {})
    order = release_order(packages, select(packages, base))
    chosen = [packages[n] for n in order]
    everything = [packages[n] for n in release_order(packages, set(packages))]
    outputs: dict[str, object] = {
        "release-order": order,
        "packages": [{"name": p.name, "dir": p.dir} for p in chosen],
        "postgres": [
            {"name": p.name, "dir": p.dir, "env": p.ci["postgres"]["env"]}
            for p in chosen
            if "postgres" in p.ci
        ],
        "smoke": [
            {"name": p.name, "extra": c["extra"], "marker": c["marker"]}
            for p in chosen
            for c in p.checks()
            if c["kind"] == "smoke"
        ],
        "suites": [
            {"name": name, "args": shlex.join(args)}
            for name, args in settings.get("suites", {}).items()
        ],
        "pytest-args": shlex.join(settings.get("pytest-args", [])),
        "cov-args": shlex.join(f"--cov={p.module}" for p in everything),
        "test-paths": shlex.join(p.dir for p in everything),
        "sonar-sources": ",".join(f"{p.dir}/src" for p in everything),
        "sonar-tests": ",".join(
            f"{p.dir}/tests" for p in everything if (ROOT / p.dir / "tests").is_dir()
        ),
        "sonar": (ROOT / "sonar-project.properties").is_file(),
        "docs": (ROOT / "mkdocs.yml").is_file(),
    }
    for key, value in outputs.items():
        print(f"{key}={value if isinstance(value, str) else json.dumps(value)}")


def releasable(ok_dir: Path, names: list[str]) -> None:
    """Print, in release order, each package whose checks all left a marker in
    `ok_dir` and whose requirements among `names` are releasable too."""
    packages = load_packages()
    selected = {normalize(n) for n in names}
    passed: set[str] = set()
    for name in release_order(packages, selected):
        package = packages[name]
        checks_ok = all((ok_dir / c["marker"]).exists() for c in package.checks())
        if checks_ok and (package.requires & selected) <= passed:
            passed.add(name)
            print(name)
        else:
            print(
                f"not releasing {name}: a check or a prerequisite failed",
                file=sys.stderr,
            )


def released() -> None:
    packages = load_packages()
    tags = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    for tag in tags:
        name, _, version = tag.rpartition("-v")
        if name in packages:
            print(name, packages[name].dir, packages[name].module, version)


IMPORT_SNIPPET = """
import importlib, runpy, sys
setup, *modules = sys.argv[1:]
if setup:
    runpy.run_path(setup)
for name in modules:
    importlib.import_module(name)
    print("imported", name)
"""


def smoke(package_name: str, extra: str) -> int:
    """Install `package_name` with only `extra` from wheels built from this checkout
    into a clean venv, then import the modules its `[tool.workspace-ci.smoke]` lists.

    Every other CI job syncs all extras, which hides an extra that forgets a
    dependency another extra brings; this installs exactly what the wheel declares.
    """
    from packaging.requirements import Requirement

    packages = load_packages()
    package = packages[normalize(package_name)]
    config = package.ci["smoke"]
    modules = [*config.get("modules", []), *(config["extras"][extra] if extra else [])]

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
                cwd=ROOT,
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
        subprocess.run(["uv", "venv", "-q", str(venv)], cwd=ROOT, check=True)
        install = ["uv", "pip", "install", "-q", "--python", str(python)]
        # Local wheels go in without deps, so their git-pinned siblings are never
        # fetched; everything else they declare is in `external`.
        if external:
            subprocess.run([*install, *sorted(external)], check=True)
        subprocess.run(
            [*install, "--no-deps", *(str(wheels[n]) for n in local)], check=True
        )
        setup = str(ROOT / package.dir / config["setup"]) if "setup" in config else ""
        return subprocess.run(
            [str(python), "-c", IMPORT_SNIPPET, setup, *modules]
        ).returncode


def main() -> int:
    command, args = sys.argv[1], sys.argv[2:]
    if command == "plan":
        plan(args[0] if args else "")
    elif command == "releasable":
        releasable(Path(args[0]), args[1:])
    elif command == "released":
        released()
    elif command == "smoke":
        return smoke(args[0], args[1] if len(args) > 1 else "")
    else:
        sys.exit(f"unknown command: {command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
