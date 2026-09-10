"""Documentation-tree checkers: the area model, structure rules, links and nav.

Every rn-forge repo lays its documentation out the same way — a small set of
*areas* (`adr`, `guides`, `reference`, ...) declared in `docs/_areas.yml`, each
with an `index.md` and a `_structure.md`, navigated from one generated
`mkdocs.yml` nav block. Four repos had each grown their own fork of the
scripts that check that (kiln ADR-0010); this package is the single
implementation they all call.

The area *keys* are deliberately not a fixed list. `docs/_areas.yml` is seeded
by the generator and then owned by the repository, so a repo may declare an
area this package has never heard of and the checks validate the tree against
whatever it declares.

- :mod:`~rn_forge.tooling.docs.areas` — the `_areas.yml` model.
- :mod:`~rn_forge.tooling.docs.markdown` — the small amount of Markdown
  parsing the checkers agree on.
- :mod:`~rn_forge.tooling.docs.structure` — the docs tree matches the model.
- :mod:`~rn_forge.tooling.docs.site` — the built site's graph resolves.
- :mod:`~rn_forge.tooling.docs.nav` — generate `mkdocs.yml`'s nav block.

Every check returns :class:`~rn_forge.commons.findings.Finding` objects, so a
caller renders them (or serialises them for ``--json``) the same way whichever
check produced them.
"""

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
