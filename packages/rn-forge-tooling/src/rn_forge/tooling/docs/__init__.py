"""Documentation area, structure, link, and navigation checks."""

from __future__ import annotations

from rn_forge.tooling.docs.areas import Area, load_areas
from rn_forge.tooling.docs.markdown import (
    headings,
    is_external,
    links,
    slugify,
    strip_fenced_code,
)
from rn_forge.tooling.docs.nav import NAV_BLOCK, build_nav, update_nav
from rn_forge.tooling.docs.site import check_site
from rn_forge.tooling.docs.structure import check_structure

__all__ = [
    "NAV_BLOCK",
    "Area",
    "build_nav",
    "check_site",
    "check_structure",
    "headings",
    "is_external",
    "links",
    "load_areas",
    "slugify",
    "strip_fenced_code",
    "update_nav",
]
