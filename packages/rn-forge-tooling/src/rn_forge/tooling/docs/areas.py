"""Models for the documentation areas declared in `docs/_areas.yml`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from rn_forge.commons.fs.documents import YamlUtils
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.dataclasses import DataclassMixin

__all__ = ["Area", "NAV_VALUES", "load_areas"]

NAV_VALUES = frozenset({"children", "index-only"})
"""Valid values of an area's ``nav`` key."""


@dataclass(frozen=True, slots=True)
class Area(DataclassMixin):
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

    Raises:
        AppException: The manifest is absent, is not a mapping, declares an
            area whose fields do not match :class:`Area`, or declares one with
            an unknown ``nav`` value.
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
        values = dict(entry)
        # `title` defaults from `key`, so it cannot be a dataclass default.
        key = values.get("key")
        if isinstance(key, str):
            values.setdefault("title", key.title())
        try:
            area = Area.from_dict(values)
        except AppException as error:
            # The class-level message names the field; only this frame knows
            # which file the author has to open.
            raise AppException("{}: {}", manifest, error) from error
        if area.nav not in NAV_VALUES:
            raise AppException(
                "{}: invalid nav value for area {!r}: {!r}",
                manifest,
                area.key,
                area.nav,
            )
        areas.append(area)
    return areas
