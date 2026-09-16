"""Typed exceptions mapped to HTTP problems by the default registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rn_forge.commons.exceptions import AppException

if TYPE_CHECKING:
    from rn_forge.web.problem import ProblemDetail

__all__ = [
    "AuthenticationFailed",
    "DomainConflict",
    "IdempotencyKeyRequired",
    "IdempotencyKeyReuse",
    "InvalidCursor",
    "MalformedPrecondition",
    "PermissionDenied",
    "PreconditionRequired",
    "RemoteProblem",
    "VersionConflict",
    "WebError",
]


class WebError(AppException):
    """Base class for every exception this package raises."""


class DomainConflict(WebError):
    """The request conflicts with the current state of the resource (409)."""


class VersionConflict(DomainConflict):
    """The client's precondition did not match the current version (412)."""


class PreconditionRequired(WebError):
    """The route requires a precondition and the client sent none (428)."""


class MalformedPrecondition(WebError):
    """The precondition header was present but could not be parsed (400)."""


class InvalidCursor(WebError):
    """The pagination token was absent from, or malformed in, the request (400)."""


class IdempotencyKeyRequired(WebError):
    """The endpoint requires an ``Idempotency-Key`` and none was sent (400)."""


class IdempotencyKeyReuse(WebError):
    """The idempotency key was replayed with a different request body (409)."""


class AuthenticationFailed(WebError):
    """No credentials were supplied, or they failed verification (401).

    The message carries the reason for the binding to log; it must never reach
    the response body, which renders :data:`~rn_forge.web.auth.AUTH_FAILED_DETAIL`.
    """


class PermissionDenied(WebError):
    """Credentials verified, but the principal lacks the required access (403)."""


class RemoteProblem(WebError):
    """An upstream service returned an ``application/problem+json`` body.

    Carries the parsed :class:`~rn_forge.web.problem.ProblemDetail` so a gateway
    can re-emit the upstream's slug rather than flattening every upstream
    failure into "internal error".

    Args:
        problem: The parsed upstream problem.
        *message_args: Forwarded to ``AppException``.
        **error_data: Forwarded to ``AppException``.
    """

    problem: ProblemDetail

    def __init__(
        self,
        problem: ProblemDetail,
        *message_args: Any,
        **error_data: Any,
    ) -> None:
        error_data.setdefault("error_code", problem.status)
        super().__init__(
            "Upstream returned a problem: {} ({})",
            problem.title,
            problem.status,
            *message_args,
            **error_data,
        )
        self.problem = problem
