"""The CI core: the member graph, change selection, check matrices and release gating.

The core knows neither a CI platform nor a package manager. An adapter fills a
`Workspace` from the repository's own manifests and formats the `plan` outputs
for its platform.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Changes under these paths select no package.
UNSCOPED = ("docs/",)

# A revision name never starts with `-`, so it cannot be read as a git option.
REVISION = r"[A-Za-z0-9_][A-Za-z0-9_./@-]*"


def normalize(name: str) -> str:
    """Return `name` in its canonical form: lowercase, runs of `-_.` as one `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    """Return the normalized package name of a requirement string."""
    return normalize(re.split(r"[\s\[<>=!~;@]", requirement.strip(), maxsplit=1)[0])


@dataclass
class Smoke:
    """A package's smoke-test declaration.

    Attributes:
        modules: Modules imported in every smoke run.
        extras: Modules imported for each extra, keyed by extra name.
        setup: A script, relative to the package directory, run before the imports.
    """

    modules: list[str] = field(default_factory=list[str])
    extras: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    setup: str = ""


@dataclass
class Package:
    """A workspace member.

    Attributes:
        name: Normalized project name.
        dir: Directory relative to the repository root, with `/` separators.
        module: Import name of the package.
        requires: Names of the workspace members this package requires.
        postgres_env: Variable that receives a PostgreSQL DSN, or `None` when the
            package needs no database run.
        smoke: The smoke-test declaration, or `None` when the package declares none.
        adapters: Names of the package's adapters, or `None` when it declares none.
    """

    name: str
    dir: str
    module: str
    requires: set[str] = field(default_factory=lambda: set[str]())
    postgres_env: str | None = None
    smoke: Smoke | None = None
    adapters: list[str] | None = None

    def checks(self) -> list[dict[str, str]]:
        """Every check that must pass before this package may be released.

        The empty-extra smoke check is listed whether or not `smoke` is set.
        """
        checks = [{"kind": "verify", "marker": f"{self.name}.verify"}]
        if self.postgres_env is not None:
            checks.append({"kind": "postgres", "marker": f"{self.name}.postgres"})
        checks.append({"kind": "smoke", "extra": "", "marker": f"{self.name}.smoke"})
        if self.smoke is not None:
            checks += [
                {
                    "kind": "smoke",
                    "extra": extra,
                    "marker": f"{self.name}.smoke-{extra}",
                }
                for extra in self.smoke.extras
            ]
        return checks


@dataclass
class Workspace:
    """A repository root, its members and its workspace-wide CI settings.

    Attributes:
        root: The repository root.
        packages: The members, keyed by normalized name.
        pytest_args: Arguments added to every package's pytest run.
        suites: Workspace-wide pytest runs, keyed by suite name.
    """

    root: Path
    packages: dict[str, Package]
    pytest_args: list[str] = field(default_factory=list[str])
    suites: dict[str, list[str]] = field(default_factory=dict[str, list[str]])


def release_order(packages: dict[str, Package], names: set[str]) -> list[str]:
    """Return `names` with every package after its internal requirements."""
    order: list[str] = []
    pending = sorted(names)
    while pending:
        ready = [n for n in pending if not (packages[n].requires & names) - set(order)]
        order += ready
        pending = [n for n in pending if n not in ready]
    return order


def changed_files(root: Path, base: str) -> list[str]:
    """Return the paths changed between `base` and `HEAD`.

    Raises:
        ValueError: When `base` is not a plain revision name.
    """
    if not re.fullmatch(REVISION, base):
        raise ValueError(f"invalid base {base!r}")
    out = subprocess.run(
        ["git", "diff", "--name-only", "--end-of-options", f"{base}...HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out.splitlines()


def select(workspace: Workspace, base: str) -> set[str]:
    """Return the packages with changed files, plus every package that depends on one.

    An empty, invalid or non-ancestor base, or a change outside every package and
    `UNSCOPED`, selects all. A base is invalid unless it matches `REVISION`.
    """
    packages, root = workspace.packages, workspace.root
    if not base:
        return set(packages)
    if not re.fullmatch(REVISION, base) or (
        subprocess.run(
            ["git", "cat-file", "-e", "--end-of-options", f"{base}^{{commit}}"],
            check=False,
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        or subprocess.run(
            ["git", "merge-base", "--is-ancestor", "--end-of-options", base, "HEAD"],
            check=False,
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
    ):
        print(
            f"base {base} is not a commit or an ancestor of HEAD; selecting all packages",
            file=sys.stderr,
        )
        return set(packages)
    selected: set[str] = set()
    for file in changed_files(root, base):
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


def plan(workspace: Workspace, base: str) -> dict[str, object]:
    """Return every job's matrix and package list for a run against `base`.

    Command-line values are shell-quoted strings. The keys are `release-order`,
    `packages`, `postgres`, `smoke`, `suites`, `pytest-args`, `cov-args`,
    `test-paths`, `sonar-sources`, `sonar-tests`, `sonar` and `docs`.
    """
    packages, root = workspace.packages, workspace.root
    order = release_order(packages, select(workspace, base))
    chosen = [packages[n] for n in order]
    everything = [packages[n] for n in release_order(packages, set(packages))]
    return {
        "release-order": order,
        "packages": [{"name": p.name, "dir": p.dir} for p in chosen],
        "postgres": [
            {"name": p.name, "dir": p.dir, "env": p.postgres_env}
            for p in chosen
            if p.postgres_env is not None
        ],
        "smoke": [
            {"name": p.name, "extra": c["extra"], "marker": c["marker"]}
            for p in chosen
            for c in p.checks()
            if c["kind"] == "smoke"
        ],
        "suites": [
            {"name": name, "args": shlex.join(args)}
            for name, args in workspace.suites.items()
        ],
        "pytest-args": shlex.join(workspace.pytest_args),
        "cov-args": shlex.join(f"--cov={p.module}" for p in everything),
        "test-paths": shlex.join(p.dir for p in everything),
        "sonar-sources": ",".join(f"{p.dir}/src" for p in everything),
        "sonar-tests": ",".join(
            f"{p.dir}/tests" for p in everything if (root / p.dir / "tests").is_dir()
        ),
        "sonar": (root / "sonar-project.properties").is_file(),
        "docs": (root / "mkdocs.yml").is_file(),
    }


def releasable(
    packages: dict[str, Package], ok_dir: Path, names: list[str]
) -> tuple[list[str], list[str]]:
    """Return the packages of `names` that may be released, then those that may not.

    A package may be released when every check of it left a marker file in
    `ok_dir` and its requirements among `names` may be released too. Both lists
    are in release order.
    """
    selected = {normalize(n) for n in names}
    passed: set[str] = set()
    blocked: list[str] = []
    for name in release_order(packages, selected):
        package = packages[name]
        checks_ok = all((ok_dir / c["marker"]).exists() for c in package.checks())
        if checks_ok and (package.requires & selected) <= passed:
            passed.add(name)
        else:
            blocked.append(name)
    return [n for n in release_order(packages, selected) if n in passed], blocked


def released(workspace: Workspace) -> list[tuple[str, str, str, str]]:
    """Return `(name, dir, module, version)` for each `<name>-v<version>` tag at `HEAD`."""
    tags = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=workspace.root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    found: list[tuple[str, str, str, str]] = []
    for tag in tags:
        name, _, version = tag.rpartition("-v")
        if name in workspace.packages:
            package = workspace.packages[name]
            found.append((name, package.dir, package.module, version))
    return found
