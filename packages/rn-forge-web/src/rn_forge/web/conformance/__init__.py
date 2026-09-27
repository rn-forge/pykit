"""Framework-independent HTTP conformance scenarios and redaction rules."""

from __future__ import annotations

from rn_forge.web.conformance.cases import CASES, case_by_id, cases_for
from rn_forge.web.conformance.types import (
    REDACTED,
    VARIABLE_MEMBERS,
    ConformanceArea,
    ConformanceCase,
    RequestSpec,
    redact,
)

__all__ = [
    "CASES",
    "REDACTED",
    "VARIABLE_MEMBERS",
    "ConformanceArea",
    "ConformanceCase",
    "RequestSpec",
    "case_by_id",
    "cases_for",
    "redact",
]
