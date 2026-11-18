"""HTTP conformance cases consumed by framework-specific test drivers."""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

from rn_forge.web.conformance._pagination import PAGINATION_CASES
from rn_forge.web.conformance._platform import PLATFORM_CASES
from rn_forge.web.conformance._problem import PROBLEM_CASES
from rn_forge.web.conformance._transfer import TRANSFER_CASES
from rn_forge.web.conformance._writes import WRITE_CASES
from rn_forge.web.conformance.types import (
    ConformanceArea,
    ConformanceCapability,
    ConformanceCase,
)

__all__ = ["CASES", "case_by_id", "cases_for", "cases_provided_by"]

CASES: Final[tuple[ConformanceCase, ...]] = (
    PROBLEM_CASES + WRITE_CASES + PAGINATION_CASES + TRANSFER_CASES + PLATFORM_CASES
)


def cases_for(area: ConformanceArea) -> tuple[ConformanceCase, ...]:
    """Return every case in *area*, in table order."""
    return tuple(case for case in CASES if case.area == area)


def case_by_id(case_id: str) -> ConformanceCase:
    """Return the case with *case_id*, for resolving ``depends_on``.

    Raises:
        KeyError: No case has that id.
    """
    for case in CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)


def cases_provided_by(
    provides: Collection[ConformanceCapability] = (),
) -> tuple[ConformanceCase, ...]:
    """Return every case whose required capabilities a binding provides.

    A case with no ``requires`` is always returned. A driver parametrizes over
    this instead of :data:`CASES`, passing the capabilities its fixture
    application serves.

    Args:
        provides: The capabilities the binding provides.

    Example::

        @pytest.mark.parametrize("case", cases_provided_by({"session-routes"}))
        def test_conforms(case): ...
    """
    available = frozenset(provides)
    return tuple(case for case in CASES if case.requires <= available)
