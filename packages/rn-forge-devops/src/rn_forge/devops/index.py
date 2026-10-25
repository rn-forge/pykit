"""A PEP 503 simple index rendered from a list of release files."""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass

_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta name="pypi:repository-version" content="1.0">
<title>{title}</title>
</head>
<body>
{links}
</body>
</html>
"""


@dataclass(frozen=True, slots=True)
class ReleaseFile:
    """One distribution file attached to a release."""

    project: str
    """The distribution name; normalized when the index is rendered."""
    filename: str
    """The file name, for example `rn_forge_commons-0.7.0-py3-none-any.whl`."""
    url: str
    """The release asset's download URL."""
    sha256: str
    """The file's hex SHA-256 digest."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _page(title: str, links: list[str]) -> str:
    return _PAGE.format(title=html.escape(title), links="\n".join(links))


def render_index(files: Sequence[ReleaseFile]) -> dict[str, str]:
    """Return the index's pages, keyed by relative path.

    `index.html` links each project, sorted. `<project>/index.html` links each
    of the project's files, sorted by filename, with a `#sha256=` fragment.
    Project names are normalized per PEP 503 and all text is HTML-escaped.
    """
    by_project: dict[str, list[ReleaseFile]] = {}
    for file in files:
        by_project.setdefault(_normalize(file.project), []).append(file)

    pages = {
        "index.html": _page(
            "Simple index",
            [
                f'<a href="{html.escape(project)}/">{html.escape(project)}</a><br>'
                for project in sorted(by_project)
            ],
        )
    }
    for project, project_files in by_project.items():
        pages[f"{project}/index.html"] = _page(
            f"Links for {project}",
            [
                f'<a href="{html.escape(f.url)}#sha256={html.escape(f.sha256)}">'
                f"{html.escape(f.filename)}</a><br>"
                for f in sorted(project_files, key=lambda f: f.filename)
            ],
        )
    return pages
