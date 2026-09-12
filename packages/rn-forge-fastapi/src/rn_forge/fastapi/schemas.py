"""pydantic mirrors of the :mod:`rn_forge.web` wire shapes, and the camelCase base.

``rn-forge-web`` ships its wire shapes as frozen dataclasses so a Django
consumer carries no pydantic. A FastAPI route needs a ``BaseModel`` to name as
its ``response_model``; these are those models, written once.

Each mirror has the JSON shape of its dataclass's wire body — a test
round-trips every one — and converts both ways with ``from_wire`` and
``to_wire``. Each is **named for the wire, not for this package**: FastAPI
names ``components/schemas`` after the class, and both stacks must emit
``ProblemDetail``, ``CheckResult`` and ``HealthReport`` verbatim.

``from __future__ import annotations`` holds here
-------------------------------------------------

The known friction — stringified annotations, pydantic, a PEP 695 generic and
FastAPI's runtime introspection — was checked rather than assumed: pydantic
resolves every field annotation against this module's globals, so the names
they use (``CheckStatus``, ``Any``) are imported at runtime and never under
``TYPE_CHECKING``.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from rn_forge.web import CheckResult as WireCheckResult
from rn_forge.web import CheckStatus
from rn_forge.web import HealthReport as WireHealthReport
from rn_forge.web import Page as WirePage
from rn_forge.web import ProblemDetail as WireProblemDetail

__all__ = ["CheckResult", "HealthReport", "Page", "ProblemDetail", "WireModel"]


class WireModel(BaseModel):
    """Base for every model that crosses the wire: camelCase out, either spelling in.

    Derive an application's own request and response models from this too. A
    casing rule held by per-model discipline holds until the first hurried
    endpoint; one held by a base class holds.

    - **Out:** ``serialize_by_alias`` makes ``model_dump()`` camelCase without
      being asked, so a hand-built ``JSONResponse(model.model_dump(mode="json"))``
      is camelCase too — not only a ``response_model``.
    - **In:** both the camelCase alias and the Python name validate, so an
      internal caller posting ``snake_case`` needs no client change.
    - RFC 9457's core members are single lowercase words, which ``to_camel``
      leaves alone.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class ProblemDetail(WireModel):
    """Mirror of :class:`rn_forge.web.ProblemDetail`.

    Extension members are **flattened at the top level** on the wire (RFC 9457
    §3.2), so the model allows extra members instead of nesting them.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    instance: str

    @classmethod
    def from_wire(cls, problem: WireProblemDetail) -> Self:
        """Build the mirror from a web problem."""
        return cls.model_validate(problem.as_body())

    def to_wire(self) -> WireProblemDetail:
        """Return the web problem, with every extra member as an extension."""
        return WireProblemDetail(
            type=self.type,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=self.instance,
            extensions=dict(self.model_extra or {}),
        )


def _is_none(value: object) -> bool:
    return value is None


class Page[T](WireModel):
    """Mirror of :class:`rn_forge.web.Page`: the AIP-158 envelope.

    ``nextPageToken`` is always present and ``null`` on the last page;
    ``totalSize`` is omitted when there is none — both exactly as the web
    dataclass's ``as_body()``.
    """

    items: list[T]
    next_page_token: str | None
    total_size: int | None = Field(default=None, exclude_if=_is_none)

    @classmethod
    def from_wire(cls, page: WirePage[T]) -> Self:
        """Build the mirror from a web page."""
        return cls.model_validate(page.as_body())

    def to_wire(self) -> WirePage[T]:
        """Return the web page."""
        return WirePage(
            items=list(self.items),
            next_page_token=self.next_page_token,
            total_size=self.total_size,
        )


class CheckResult(WireModel):
    """Mirror of :class:`rn_forge.web.CheckResult`."""

    status: CheckStatus
    reason: str | None = None
    remediation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict[str, Any])

    @classmethod
    def from_wire(cls, result: WireCheckResult) -> Self:
        """Build the mirror from a web check result."""
        return cls.model_validate(result)

    def to_wire(self) -> WireCheckResult:
        """Return the web check result."""
        return WireCheckResult(
            status=self.status,
            reason=self.reason,
            remediation=self.remediation,
            details=dict(self.details),
        )


class HealthReport(WireModel):
    """Mirror of :class:`rn_forge.web.HealthReport`.

    ``http_status`` is not a field: the web report deliberately keeps it off the
    wire, so :meth:`to_wire` takes it as an argument.
    """

    status: CheckStatus
    checks: dict[str, CheckResult]

    @classmethod
    def from_wire(cls, report: WireHealthReport) -> Self:
        """Build the mirror from a web health report."""
        return cls.model_validate(report.as_body())

    def to_wire(self, *, http_status: int) -> WireHealthReport:
        """Return the web health report, which carries the HTTP status to serve."""
        return WireHealthReport(
            status=self.status,
            checks={name: result.to_wire() for name, result in self.checks.items()},
            http_status=http_status,
        )
