"""Typed exceptions mapped to HTTP problems by the default registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rn_forge.commons.exceptions import AppException

if TYPE_CHECKING:
    from rn_forge.web.problem import ProblemDetail

__all__ = [
    "AuthenticationFailed",
    "ContentTooLarge",
    "DomainConflict",
    "IdempotencyKeyInFlight",
    "IdempotencyKeyRequired",
    "IdempotencyKeyReuse",
    "InvalidCursor",
    "MalformedPrecondition",
    "PermissionDenied",
    "PreconditionRequired",
    "RemoteProblem",
    "ServiceUnavailable",
    "TooManyRequests",
    "VersionConflict",
    "WebError",
]


class WebError(AppException):
    """Base class for every exception this package raises."""


class DomainConflict(WebError):
    """The request conflicts with the current state of the resource (409)."""


class VersionConflict(WebError):
    """The client's precondition did not match the current version (412)."""


class PreconditionRequired(WebError):
    """The route requires a precondition and the client sent none (428)."""


class MalformedPrecondition(WebError):
    """The precondition header was present but could not be parsed (400)."""


class InvalidCursor(WebError):
    """The pagination token was absent from, or malformed in, the request (400)."""


class ContentTooLarge(WebError):
    """The request body exceeds the configured size limit (413)."""


class IdempotencyKeyRequired(WebError):
    """The endpoint requires an ``Idempotency-Key`` and none was sent (400)."""


class IdempotencyKeyReuse(WebError):
    """The idempotency key was replayed with a different request body (422)."""


class IdempotencyKeyInFlight(WebError):
    """The idempotency key was claimed and its original request has not completed (409)."""


class AuthenticationFailed(WebError):
    """No credentials were supplied, or they failed verification (401).

    The message carries the reason for the binding to log; it must never reach
    the response body, which renders :data:`~rn_forge.web.auth.AUTH_FAILED_DETAIL`.
    """


class PermissionDenied(WebError):
    """Credentials verified, but the principal lacks the required access (403)."""


class TooManyRequests(WebError):
    """The client has sent too many requests in a given time (429).

    Args:
        *message_args: Forwarded to ``AppException``.
        retry_after: Seconds the client should wait before retrying, carried
            as a ``Retry-After`` response header. ``None`` sends no header.
        **error_data: Forwarded to ``AppException``.
    """

    retry_after: int | None

    def __init__(
        self,
        *message_args: Any,
        retry_after: int | None = None,
        **error_data: Any,
    ) -> None:
        super().__init__(*message_args, **error_data)
        self.retry_after = retry_after

    def response_headers(self) -> dict[str, str]:
        """Return the ``Retry-After`` header, or nothing when unset."""
        return (
            {} if self.retry_after is None else {"Retry-After": str(self.retry_after)}
        )


class ServiceUnavailable(WebError):
    """The service cannot handle the request right now (503).

    Args:
        *message_args: Forwarded to ``AppException``.
        retry_after: Seconds the client should wait before retrying, carried
            as a ``Retry-After`` response header. ``None`` sends no header.
        **error_data: Forwarded to ``AppException``.
    """

    retry_after: int | None

    def __init__(
        self,
        *message_args: Any,
        retry_after: int | None = None,
        **error_data: Any,
    ) -> None:
        super().__init__(*message_args, **error_data)
        self.retry_after = retry_after

    def response_headers(self) -> dict[str, str]:
        """Return the ``Retry-After`` header, or nothing when unset."""
        return (
            {} if self.retry_after is None else {"Retry-After": str(self.retry_after)}
        )


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
