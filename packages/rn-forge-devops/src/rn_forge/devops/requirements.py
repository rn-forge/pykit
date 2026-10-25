"""Check that requirements between workspace members are version ranges."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

MANIFEST = "pyproject.toml"


def _members(root: Path) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Map each member's canonical name to its name, version and manifest."""
    workspace: dict[str, Any] = tomllib.loads((root / MANIFEST).read_text())["tool"][
        "uv"
    ]["workspace"]
    excluded = {
        path
        for pattern in workspace.get("exclude", [])
        for path in root.glob(f"{pattern}/{MANIFEST}")
    }
    members: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for pattern in workspace["members"]:
        for path in sorted(root.glob(f"{pattern}/{MANIFEST}")):
            if path in excluded:
                continue
            manifest: dict[str, Any] = tomllib.loads(path.read_text())
            project: dict[str, Any] = manifest["project"]
            name: str = project["name"]
            members[canonicalize_name(name)] = (
                name,
                project.get("version", ""),
                manifest,
            )
    return members


def _requirements(project: dict[str, Any], groups: dict[str, Any]) -> list[str]:
    """Return every requirement string of one member's manifest."""
    found: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        found.extend(extra)
    for group in groups.values():
        found.extend(item for item in group if isinstance(item, str))
    return found


def check_requirements(root: Path) -> list[str]:
    """Return the problems with requirements on other workspace members.

    Reads the members listed under `[tool.uv.workspace]` in `root/pyproject.toml`.
    A requirement on a member, in `dependencies`, `optional-dependencies` or
    `[dependency-groups]`, is reported when it is a URL, when its specifier
    excludes the member's `[project]` version, or when its specifier has no
    `<` or `<=` clause. Requirements on anything else are ignored.

    Args:
        root: The workspace root directory.

    Returns:
        One message per problem, empty when the requirements are all ranges.
    """
    members = _members(root)
    problems: list[str] = []
    for key, (name, _, manifest) in members.items():
        for text in _requirements(
            manifest["project"], manifest.get("dependency-groups", {})
        ):
            req = Requirement(text)
            target_key = canonicalize_name(req.name)
            target = members.get(target_key)
            # A package naming itself (an extra that includes other extras) is no dependency.
            if target is not None and target_key != key:
                problems.extend(_problems(name, req, target[1]))
    return problems


def _problems(package: str, req: Requirement, version: str) -> list[str]:
    if req.url is not None:
        return [f"{package}: {req.name} is a URL; use a range (ADR-0004)"]
    spec = req.specifier
    shown = f"{req.name}{spec}"
    if version and not spec.contains(Version(version), prereleases=True):
        return [f"{package}: {shown} excludes the workspace's {version}"]
    if not any(clause.operator in ("<", "<=") for clause in spec):
        return [f"{package}: {shown} has no ceiling"]
    return []
