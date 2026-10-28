"""The security-control case list matches the design's table."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rn_forge.auth.conformance import CASES, case_by_id, tagged_tests

pytestmark = pytest.mark.unit

DESIGN = Path(__file__).resolve().parents[3] / "docs/specs/epics/E13-auth/design.md"


def _rows() -> list[str]:
    text = DESIGN.read_text()
    section = text.split("\n## Security controls\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    return rows[2:]  # header and separator


def test_ids_are_unique_and_kebab_case() -> None:
    ids = [case.id for case in CASES]

    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", i) for i in ids)


def test_there_is_one_case_per_row_of_the_design_table() -> None:
    if not DESIGN.exists():
        pytest.skip("the design document is not part of an installed package")

    assert len(CASES) == len(_rows())


def test_case_by_id_returns_the_case_and_rejects_an_unknown_id() -> None:
    assert case_by_id("rate-limiting") in CASES
    with pytest.raises(KeyError):
        case_by_id("nope")


def test_tagged_tests_finds_markers_on_functions_methods_and_classes(
    tmp_path: Path,
) -> None:
    (tmp_path / "test_a.py").write_text(
        "import pytest\n"
        "@pytest.mark.security_control('rate-limiting', 'audit-events')\n"
        "def test_one(): ...\n"
        "@pytest.mark.security_control('csrf-and-origin')\n"
        "class TestTwo:\n"
        "    @pytest.mark.security_control('jwks-rotation')\n"
        "    async def test_three(self): ...\n"
        "@pytest.mark.unit\n"
        "def test_four(): ...\n"
    )

    assert tagged_tests(tmp_path) == {
        "rate-limiting": ["test_a.py::test_one"],
        "audit-events": ["test_a.py::test_one"],
        "csrf-and-origin": ["test_a.py::TestTwo"],
        "jwks-rotation": ["test_a.py::test_three"],
    }
