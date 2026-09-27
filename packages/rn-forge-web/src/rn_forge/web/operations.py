"""Long-running operations in the AIP-151 shape, with an RFC 9457 error."""

from __future__ import annotations

from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from rn_forge.web.models import WireModel
from rn_forge.web.problem import ProblemDetail

__all__ = ["Operation"]


def _is_none(value: object) -> bool:
    return value is None


class Operation(WireModel):
    """The resource a long-running call returns and a client polls.

    The call answers ``202`` with a ``Location`` naming this resource. While
    ``done`` is false neither ``error`` nor ``response`` is set; once it is true
    exactly one of them is. Absent members are omitted from the body.

    Example:
        ``Operation(name="operations/7", done=True, response={"id": "1"}).as_body()``
        returns ``{"name": "operations/7", "done": True, "response": {"id": "1"}}``.

    Raises:
        pydantic.ValidationError: When ``done`` is false and an outcome is set,
            or true and not exactly one is.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    done: bool = False
    metadata: dict[str, Any] | None = Field(default=None, exclude_if=_is_none)
    error: ProblemDetail | None = Field(default=None, exclude_if=_is_none)
    response: dict[str, Any] | None = Field(default=None, exclude_if=_is_none)

    @model_validator(mode="after")
    def _outcome_matches_done(self) -> Self:
        outcomes = (self.error is not None) + (self.response is not None)
        if outcomes != (1 if self.done else 0):
            raise ValueError(
                "a finished operation has exactly one of error and response; "
                "an unfinished one has neither"
            )
        return self

    def as_body(self) -> dict[str, Any]:
        """Return the wire body, camelCase, omitting absent members."""
        return self.model_dump()
