"""Layout and import boundaries for the conformance case table."""

import ast
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import rn_forge.web.conformance.cases as cases_module
from rn_forge.web import conformance
from rn_forge.web.conformance import CASES, case_by_id, cases_for

pytestmark = pytest.mark.unit

TESTS = Path(__file__).parent
PACKAGE = TESTS.parent
CONFORMANCE = PACKAGE / "src" / "rn_forge" / "web" / "conformance"
GROUPS = (
    ("_problem", "PROBLEM_CASES"),
    ("_writes", "WRITE_CASES"),
    ("_pagination", "PAGINATION_CASES"),
    ("_transfer", "TRANSFER_CASES"),
    ("_platform", "PLATFORM_CASES"),
)
GROUP_NAMES = tuple(name for name, _ in GROUPS)
PUBLIC_NAMES = [
    "CASES",
    "REDACTED",
    "VARIABLE_MEMBERS",
    "ConformanceArea",
    "ConformanceCapability",
    "ConformanceCase",
    "RequestSpec",
    "case_by_id",
    "cases_for",
    "cases_provided_by",
    "redact",
]
CASE_PUBLIC_NAMES = ["CASES", "case_by_id", "cases_for", "cases_provided_by"]
FRAMEWORK_MODULES = {
    "django",
    "rest_framework",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "tablib",
    "pytest",
    "assertpy",
}


def _fixture_rows() -> list[tuple[str, str]]:
    return [
        tuple(line.split("\t", maxsplit=1))
        for line in (TESTS / "data" / "conformance_case_ids.txt")
        .read_text()
        .splitlines()
    ]


def test_case_ids_are_unchanged():
    expected = _fixture_rows()
    actual = {(case.area, case.id) for case in CASES}
    assert len(CASES) == 118
    assert len(expected) == 118
    assert actual == set(expected)


def test_each_area_keeps_its_case_order():
    expected_by_area: dict[str, list[str]] = {}
    for area, case_id in _fixture_rows():
        expected_by_area.setdefault(area, []).append(case_id)

    for area, expected_ids in expected_by_area.items():
        assert [case.id for case in cases_for(area)] == expected_ids


def test_public_surface_is_unchanged():
    assert conformance.__all__ == PUBLIC_NAMES
    assert cases_module.__all__ == CASE_PUBLIC_NAMES


def test_conformance_pulls_in_no_framework():
    code = (
        "import sys; import rn_forge.web.conformance; "
        f"blocked = {sorted(FRAMEWORK_MODULES)!r}; "
        "assert not {name.split('.')[0] for name in sys.modules} & set(blocked)"
    )
    subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )


def test_groups_partition_the_areas():
    group_cases = []
    area_owners: dict[str, str] = {}
    for module_name, tuple_name in GROUPS:
        module = importlib.import_module(f"rn_forge.web.conformance.{module_name}")
        items = getattr(module, tuple_name)
        assert isinstance(items, tuple)
        group_cases.extend(items)
        for area in {case.area for case in items}:
            assert area not in area_owners
            area_owners[area] = module_name

    assert set(area_owners) == {area for area, _ in _fixture_rows()}
    assert tuple(group_cases) == CASES
    for case in group_cases:
        for dependency_id in case.depends_on:
            assert case_by_id(dependency_id).id == dependency_id


def test_group_modules_import_only_policy():
    module_paths = [CONFORMANCE / f"{name}.py" for name in (*GROUP_NAMES, "_shared")]
    assert all(path.is_file() for path in module_paths)

    stdlib = sys.stdlib_module_names
    for path in CONFORMANCE.glob("_*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""),
                        "rn_forge.web.conformance",
                    )
                else:
                    base = node.module or ""
                imported = [base]
            else:
                continue
            for name in imported:
                root = name.split(".", maxsplit=1)[0]
                assert (
                    root in stdlib
                    or name.startswith(("rn_forge.web.", "rn_forge.commons."))
                    or name == "rn_forge.web"
                    or name == "rn_forge.commons"
                ), f"{path.name} imports disallowed module {name}"
