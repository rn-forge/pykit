"""Tests for `rn_forge.devops.notes`."""

from __future__ import annotations

from pathlib import Path

from rn_forge.devops.notes import Umbrella, pending_umbrella


def _page(releases: Path, number: int, status: str, shipped: str = "Done.") -> None:
    page = releases / f"release-{number}" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        f"# Release {number} — title\n\n| | |\n| -- | -- |\n"
        f"| **Status** | {status} |\n\n## Scope\n\nScope.\n\n"
        f"## Shipped\n\n{shipped}\n\n## Later\n\nLater.\n",
        encoding="utf-8",
    )


def test_picks_highest_shipped_over_planned(tmp_path: Path) -> None:
    _page(tmp_path, 5, "shipped")
    _page(tmp_path, 6, "shipped 2026-10-25")
    _page(tmp_path, 7, "planned")
    found = pending_umbrella(tmp_path, {"release-5"}, "https://x.test/")
    assert found is not None
    assert (found.tag, found.title) == ("release-6", "Release 6 — title")


def test_none_when_tag_exists(tmp_path: Path) -> None:
    _page(tmp_path, 6, "shipped")
    assert pending_umbrella(tmp_path, {"release-6"}, "https://x.test/") is None


def test_none_without_shipped_page(tmp_path: Path) -> None:
    _page(tmp_path, 7, "planned")
    assert pending_umbrella(tmp_path, set(), "https://x.test/") is None


def test_body_is_shipped_section_and_link(tmp_path: Path) -> None:
    _page(tmp_path, 6, "shipped", shipped="Line one.\n\n| a | b |")
    found = pending_umbrella(tmp_path, set(), "https://x.test/pykit/")
    assert found == Umbrella(
        "release-6",
        "Release 6 — title",
        "Line one.\n\n| a | b |\n\n"
        "Release page: https://x.test/pykit/releases/release-6/\n",
    )
