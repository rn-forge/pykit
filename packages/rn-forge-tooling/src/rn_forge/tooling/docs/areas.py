"""The docs area model: `docs/_areas.yml` and what it declares.

An *area* is one top-level directory under `docs/`. The manifest names it,
titles it, says how it appears in the nav and whether it is optional or
generated. Everything else about the tree is derived from the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from rn_forge.commons.documents import YamlUtils
from rn_forge.commons.exceptions import AppException

__all__ = ["Area", "NAV_VALUES", "load_areas"]

NAV_VALUES = frozenset({"children", "index-only"})
"""Valid values of an area's ``nav`` key."""


@dataclass(frozen=True, slots=True)
class Area:
    """One declared documentation area.

    Args:
        key: The directory name under `docs/`.
        title: The nav heading for the area.
        nav: ``"children"`` to list the area's pages, ``"index-only"`` to show
            only its `index.md`.
        optional: The area may be absent without that being a finding.
        generated: The area's contents are produced by a generator (API
            reference output) — never checked, and only navigated if present.
    """

    key: str
    title: str
    nav: str = "children"
    optional: bool = False
    generated: bool = False


def load_areas(docs_root: str | Path) -> list[Area]:
    """Load `docs/_areas.yml`.

    A missing manifest raises rather than defaulting: a repo with no declared
    area model is a finding for the caller to report, not something to paper
    over with a built-in list that may not match the tree.

    Raises:
        AppException: The manifest is absent, is not a mapping, or declares an
            area with an unknown ``nav`` value.
    """
    manifest = Path(docs_root) / "_areas.yml"
    if not manifest.is_file():
        raise AppException("{} does not exist", manifest)

    raw: Any = YamlUtils.read_file(manifest)
    if not isinstance(raw, dict):
        raise AppException("{}: expected a mapping at the top level", manifest)
    document = cast(dict[str, Any], raw)

    areas: list[Area] = []
    declared = cast(list[dict[str, Any]], document.get("areas") or [])
    for entry in declared:
        key = str(entry["key"])
        nav = str(entry.get("nav", "children"))
        if nav not in NAV_VALUES:
            raise AppException(
                "{}: invalid nav value for area {!r}: {!r}", manifest, key, nav
            )
        areas.append(
            Area(
                key=key,
                title=str(entry.get("title", key.title())),
                nav=nav,
                optional=bool(entry.get("optional", False)),
                generated=bool(entry.get("generated", False)),
            )
        )
    return areas
