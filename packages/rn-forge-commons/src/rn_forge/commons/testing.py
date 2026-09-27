"""Test utilities: a persistent output-path fixture and assertpy integration.

Intended for use in ``conftest.py`` or test files — not imported by the main
package at runtime.

Usage::

    # conftest.py
    from rn_forge.commons.testing import output_path  # noqa: F401 — registers fixture

    # test_something.py
    from rn_forge.commons.testing import assert_that, soft_assertions

    def test_example(output_path):
        result_file = output_path / "result.json"
        result_file.write_text('{"ok": true}')
        assert_that(result_file.read_text()).contains("ok")

Optional dependency: ``assertpy``.
Install with ``pip install rn-forge-commons[testing]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn, cast

import pytest

__all__ = [
    "assert_that",
    "output_path",
    "raise_",
    "soft_assertions",
]


def raise_(exc: BaseException) -> NoReturn:
    """Raise *exc*; usable from a ``lambda`` where a statement is not allowed."""
    raise exc


# ---------------------------------------------------------------------------
# output_path — persistent per-test output directory
# ---------------------------------------------------------------------------


@pytest.fixture
def output_path(request: pytest.FixtureRequest) -> Path:
    """Provide a persistent, per-test output directory under ``.out/<scope>/tests/output/``.

    Unlike ``tmp_path``, the directory is **not** cleaned up after the test
    run — useful for inspecting generated files when debugging failures.

    Path format: ``<rootdir>/.out/<scope>/tests/output/<sanitised-node-id>/``

    Import this fixture into ``conftest.py`` to make it available project-wide::

        # conftest.py
        from rn_forge.commons.testing import output_path  # noqa: F401
    """
    root = Path(str(request.config.rootpath))
    node_path = Path(cast(str, request.node.nodeid).split("::", maxsplit=1)[0])  # pyright: ignore[reportUnknownMemberType]  # pytest stubs gap
    if len(node_path.parts) >= 2 and node_path.parts[0] == "packages":
        scope = node_path.parts[1]
    else:
        scope = "workspace"
    base = root / ".out" / scope / "tests" / "output"
    safe = (
        cast(str, request.node.nodeid)  # pyright: ignore[reportUnknownMemberType]  # pytest stubs gap
        .replace("/", "_")
        .replace("::", "_")
        .replace("[", "_")
        .replace("]", "")
        .replace(".py", "")
    )
    path = base / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# assertpy integration
# ---------------------------------------------------------------------------


def assert_that(val: Any, description: str = "") -> Any:
    """Begin a fluent assertpy assertion chain on *val*.

    Supports chaining multiple assertions in a single readable statement::

        assert_that("foobar").is_length(6).starts_with("foo").ends_with("bar")
        assert_that([1, 2, 3]).is_not_empty().contains(2).is_sorted()
        assert_that(path).exists().is_file()

    Args:
        val: The value under test.
        description: Optional label included in failure messages.

    Raises:
        ImportError: If ``assertpy`` is not installed.
    """
    _check_assertpy_available()
    from assertpy import assert_that as _assert_that

    return _assert_that(val, description=description)


def soft_assertions() -> Any:
    """Return a context manager that collects all assertion failures before raising.

    Use when you want to verify multiple conditions and see all failures at
    once rather than stopping at the first::

        with soft_assertions():
            assert_that(response.status_code).is_equal_to(200)
            assert_that(response.json()).contains_key("data")
            assert_that(result.count).is_greater_than(0)

    Raises:
        ImportError: If ``assertpy`` is not installed.
    """
    _check_assertpy_available()
    from assertpy import soft_assertions as _soft_assertions

    return _soft_assertions()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_assertpy_available() -> None:
    """Raise a helpful ImportError if assertpy is not installed."""
    try:
        import assertpy  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError:
        raise ImportError(
            "assert_that and soft_assertions require 'assertpy'. "
            "Install it with: pip install assertpy  "
            "(or add 'rn-forge-commons[testing]' to your dependencies)"
        ) from None
