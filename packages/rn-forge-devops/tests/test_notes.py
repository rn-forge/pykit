"""Tests for `rn_forge.devops.notes`."""

from __future__ import annotations

from pathlib import Path

import pytest

from rn_forge.devops.notes import Umbrella, changelog_section, pending_umbrella

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Next.

## [0.7.10] - 2026-10-30

### Changed

- Ten.

## [0.7.1] - 2026-10-26

### Changed

- One.

## [0.7.0]

### Added

- Zero.
"""


def test_section_stops_at_next_heading() -> None:
    assert changelog_section(CHANGELOG, "0.7.1") == "### Changed\n\n- One."


def test_last_section_runs_to_end_of_file() -> None:
    assert changelog_section(CHANGELOG, "0.7.0") == "### Added\n\n- Zero."


def test_dated_heading_matches() -> None:
    assert "- Ten." in changelog_section(CHANGELOG, "0.7.10")


def test_version_matches_exactly() -> None:
    assert "- Ten." not in changelog_section(CHANGELOG, "0.7.1")


def test_missing_version_raises() -> None:
    with pytest.raises(ValueError, match="0.9.0"):
        changelog_section(CHANGELOG, "0.9.0")


def test_empty_section_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        changelog_section("## [1.0.0] - 2026-01-01\n\n## [0.9.0]\n\n- x\n", "1.0.0")


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
