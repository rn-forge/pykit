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
    "correlation",
]
"""The eight areas §11.2 of the web plan requires coverage in."""

REDACTED: Final = "<redacted>"
"""What :func:`redact` substitutes for a member that legitimately varies."""

VARIABLE_MEMBERS: Final = frozenset({"instance", "correlation_id", "timestamp"})
"""Body members that differ per request and must not be compared literally.

``instance`` is the request path plus, in practice, an id the driver chose;
``correlation_id`` is generated; ``timestamp`` is the clock. Everything else in
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

    ``expect_headers`` is compared case-insensitively on the field name and
    exactly on the value. ``expect_body`` is compared for equality *after*
    :func:`redact`, so a member listed in :data:`VARIABLE_MEMBERS` need only be
    present, not equal.

    ``expect_absent_headers`` is the negative half, and it carries real weight:
    a 403 that wrongly emits a ``WWW-Authenticate`` challenge is a
    specification violation no positive assertion catches.

    ``depends_on`` names cases whose requests must be issued, in order, before
    this one — a replay only replays something. It is stated as data rather
    than left to the order of the table, because a driver running under a
    randomizing test runner would otherwise pass or fail by luck.
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
