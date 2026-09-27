"""Print `<short-name>=true|false` for each workspace package, for `$GITHUB_OUTPUT`.

A package is selected when a file under its directory changed, or when any package it
depends on is selected. Internal requirements are read from each manifest's dependencies,
optional dependencies and dependency groups. A change outside `packages/` and `docs/`
selects every package, as does an empty base (manual runs).

Usage: changed_packages.py [BASE_REF]
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

PREFIX = "rn-forge-"
ROOT = Path(__file__).resolve().parents[2]


def requirement_name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;@]", requirement, maxsplit=1)[0]


def internal_requirements(manifest: dict) -> set[str]:
    requirements: list[str] = list(manifest["project"].get("dependencies", []))
    for extra in manifest["project"].get("optional-dependencies", {}).values():
        requirements += extra
    for group in manifest.get("dependency-groups", {}).values():
        requirements += [item for item in group if isinstance(item, str)]
    return {name for name in map(requirement_name, requirements) if name.startswith(PREFIX)}


def load_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in sorted((ROOT / "packages").glob("*/pyproject.toml")):
        manifest = tomllib.loads(path.read_text())
        name = manifest["project"]["name"]
        graph[name] = internal_requirements(manifest) - {name}
    return graph


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out.splitlines()


def select(graph: dict[str, set[str]], base: str) -> set[str]:
    if not base:
        return set(graph)
    selected: set[str] = set()
    for file in changed_files(base):
        parts = file.split("/")
        if parts[0] == "packages" and len(parts) > 2 and parts[1] in graph:
            selected.add(parts[1])
        elif parts[0] not in ("packages", "docs"):
            return set(graph)
    grew = True
    while grew:
        grew = False
        for name, requires in graph.items():
            if name not in selected and requires & selected:
                selected.add(name)
                grew = True
    return selected


def main() -> None:
    graph = load_graph()
    selected = select(graph, sys.argv[1] if len(sys.argv) > 1 else "")
    for name in sorted(graph):
        print(f"{name.removeprefix(PREFIX)}={'true' if name in selected else 'false'}")


if __name__ == "__main__":
    main()
