"""Check that requirements between workspace members are version ranges."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

MANIFEST = "pyproject.toml"


class InvalidManifest(ValueError):
    """A workspace manifest contains invalid input for requirement checks."""


def find_root(start: Path) -> Path:
    """Return the nearest directory at or above `start` whose `pyproject.toml`
    declares `[tool.uv.workspace]`.

    Raises:
        FileNotFoundError: When there is none.
    """
    for directory in (start, *start.parents):
        manifest = directory / MANIFEST
        if manifest.is_file() and "workspace" in tomllib.loads(
            manifest.read_text()
        ).get("tool", {}).get("uv", {}):
            return directory
    raise FileNotFoundError(f"no uv workspace at or above {start}")


def _read_member(path: Path) -> tuple[str, str, dict[str, Any]]:
    manifest: dict[str, Any] = tomllib.loads(path.read_text())
    if "project" not in manifest:
        raise InvalidManifest(f"{path}: missing [project]")
    project: dict[str, Any] = manifest["project"]
    if "name" not in project:
        raise InvalidManifest(f"{path}: missing [project].name")
    name: str = project["name"]
    version: str = project.get("version", "")
    if "version" in project:
        try:
            Version(version)
        except InvalidVersion as error:
            raise InvalidManifest(f"{path}: {error}") from error
    return name, version, manifest


def _members(root: Path) -> dict[str, tuple[str, str, dict[str, Any], Path]]:
    """Map each canonical name to its name, version, manifest and path."""
    workspace: dict[str, Any] = tomllib.loads((root / MANIFEST).read_text())["tool"][
        "uv"
    ]["workspace"]
    if "members" not in workspace:
        raise InvalidManifest(f"{root / MANIFEST}: workspace lacks members")
    excluded = {
        path
        for pattern in workspace.get("exclude", [])
        for path in root.glob(f"{pattern}/{MANIFEST}")
    }
    members: dict[str, tuple[str, str, dict[str, Any], Path]] = {}
    for pattern in workspace["members"]:
        for path in sorted(root.glob(f"{pattern}/{MANIFEST}")):
            if path in excluded:
                continue
            name, version, manifest = _read_member(path)
            members[canonicalize_name(name)] = (
                name,
                version,
                manifest,
                path,
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
    Checks `dependencies`, every `optional-dependencies` list and string items
    in `[dependency-groups]`. Names are canonicalized, extras are accepted and
    markers are ignored. A requirement on another member is reported when it
    is a direct URL or path, excludes the member's `[project].version`, or has
    no `<` or `<=` ceiling; `~=` and `==` alone have no ceiling.

    Non-members (including excluded members), self-references, `include-group`
    entries and member globs matching no manifest are skipped. A member with
    no version skips only the version check; its ceiling is still checked.

    Args:
        root: The workspace root directory.

    Returns:
        One message per problem, empty when the requirements are all ranges.

    Raises:
        InvalidManifest: A requirement is malformed, a member lacks `[project]`
            or `name`, a version is unparsable, or the workspace lacks `members`.
            The message names the manifest and any malformed requirement text;
            no result is returned for invalid input.
    """
    members = _members(root)
    problems: list[str] = []
    for key, (name, _, manifest, path) in members.items():
        for text in _requirements(
            manifest["project"], manifest.get("dependency-groups", {})
        ):
            try:
                req = Requirement(text)
            except InvalidRequirement as error:
                raise InvalidManifest(
                    f"{path}: invalid requirement {text!r}: {error}"
                ) from error
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
