"""The shapes a conformance case is written in, and the redaction rule."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal, cast

__all__ = [
    "REDACTED",
    "VARIABLE_MEMBERS",
    "ConformanceArea",
    "ConformanceCase",
    "RequestSpec",
    "redact",
]

type ConformanceArea = Literal[
    "problem",
    "concurrency",
    "pagination",
    "idempotency",
    "health",
    "auth",
    "casing",
    "tracing",
    "deprecation",
    "discovery",
    "security",
    "cors",
]
"""Areas covered by the conformance suite."""

REDACTED: Final = "<redacted>"
"""What :func:`redact` substitutes for a member that legitimately varies."""

VARIABLE_MEMBERS: Final = frozenset({"instance", "trace_id", "timestamp"})
"""Body members that differ per request and must not be compared literally.

``instance`` is the request path plus, in practice, an id the driver chose;
``trace_id`` is generated per request (or per trace, when a caller's
``traceparent`` continues one); ``timestamp`` is the clock. Everything else in
a response body is part of the contract and is compared exactly.
"""


@dataclass(frozen=True)
class RequestSpec:
    """The request a driver must issue.

    ``path`` is relative to whatever base the driver mounts the fixture app
    at, and always begins with ``/``.
    """

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    query: Mapping[str, str] = field(default_factory=dict[str, str])
    body: Any = None


@dataclass(frozen=True)
class ConformanceCase:
    """One wire decision, expressed as a request and the response it must get.

    Header names are compared case-insensitively and values exactly. Bodies are
    compared after :func:`redact`. ``depends_on`` names prerequisite requests
    in execution order.
    """

    id: str
    area: ConformanceArea
    description: str
    request: RequestSpec
    expect_status: int
    depends_on: tuple[str, ...] = ()
    expect_headers: Mapping[str, str] = field(default_factory=dict[str, str])
    expect_absent_headers: frozenset[str] = frozenset()
    expect_body: Mapping[str, Any] = field(default_factory=dict[str, Any])
    expect_header_patterns: Mapping[str, str] = field(default_factory=dict[str, str])
    """Header name → regular expression, matched with ``re.fullmatch`` against
    the header value. Header names are compared case-insensitively, as for
    :attr:`expect_headers`. Used where the exact value is not deterministic
    (a generated span id in ``traceresponse``)."""


def redact(body: Mapping[str, Any]) -> dict[str, Any]:
    """Blank the members that legitimately differ per request.

    Recurses into nested mappings and lists, so a problem body's extensions and
    a page's items are covered too. Idempotent: redacting an already-redacted
    body returns the same thing, which is what makes it safe for a driver to
    apply without knowing whether the table's expectation was already redacted.
    """
    return {k: _redact_value(k, v) for k, v in body.items()}


def _redact_value(key: str, value: Any) -> Any:
    """Redact one member, recursing through containers."""
    if key in VARIABLE_MEMBERS:
        return REDACTED
    if isinstance(value, Mapping):
        return redact(cast("Mapping[str, Any]", value))
    if isinstance(value, list):
        return [
            redact(cast("Mapping[str, Any]", item))
            if isinstance(item, Mapping)
            else item
            for item in cast("list[Any]", value)
        ]
    return value
