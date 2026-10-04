"""Typed exceptions mapped to HTTP problems by the default registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rn_forge.commons.exceptions import AppException

if TYPE_CHECKING:
    from rn_forge.web.problem import ProblemDetail
    from rn_forge.web.transfer import RowError

__all__ = [
    "AuthenticationFailed",
    "ContentTooLarge",
    "DomainConflict",
    "IdempotencyKeyInFlight",
    "IdempotencyKeyRequired",
    "IdempotencyKeyReuse",
    "InvalidBatchGet",
    "InvalidCursor",
    "InvalidMergePatch",
    "InvalidOrderBy",
    "ItemsDenied",
    "MalformedPrecondition",
    "PermissionDenied",
    "PreconditionRequired",
    "RemoteProblem",
    "RowsInvalid",
    "ServiceUnavailable",
    "TooManyRequests",
    "UnsupportedMediaType",
    "VersionConflict",
    "WebError",
]


_UNSUPPORTED_MEDIA_TYPE_DETAIL = (
    "Use Content-Type: application/merge-patch+json for PATCH"
)


class WebError(AppException):
    """Base class for every exception this package raises."""


class DomainConflict(WebError):
    """The request conflicts with the current state of the resource (409)."""


class _PointedError(WebError):
    """A :class:`WebError` that may carry ``errors`` entries for the problem body.

    Args:
        *message_args: Forwarded to ``AppException``.
        errors: Validation-error entries (see :func:`~rn_forge.web.field_error`)
            emitted as the problem's ``errors`` member. ``None`` emits nothing.
        **error_data: Forwarded to ``AppException``.
    """

    def __init__(
        self,
        *message_args: Any,
        errors: Sequence[Mapping[str, str]] | None = None,
        **error_data: Any,
    ) -> None:
        super().__init__(*message_args, **error_data)
        self.errors = errors

    def problem_extensions(self) -> Mapping[str, Any]:
        """Return the ``errors`` member when one was given."""
        return {} if self.errors is None else {"errors": list(self.errors)}


class VersionConflict(_PointedError):
    """The client's precondition did not match the current version (412)."""


class PreconditionRequired(_PointedError):
    """The route requires a precondition and the client sent none (428)."""


class MalformedPrecondition(_PointedError):
    """The precondition header was present but could not be parsed (400)."""


class InvalidCursor(WebError):
    """The pagination token was absent from, or malformed in, the request (400)."""


class InvalidBatchGet(WebError):
    """A ``:batchGet`` request's ``ids`` parameter is missing or over the row cap (400)."""


class InvalidOrderBy(WebError):
    """``orderBy`` names a field the endpoint cannot sort by, or is malformed (400)."""


class ContentTooLarge(WebError):
    """The request body exceeds the configured size limit (413)."""


class UnsupportedMediaType(WebError):
    """The request's media type is not one the route accepts (415).

    The message defaults to ``Use Content-Type: application/merge-patch+json for PATCH``.
    """

    def __init__(
        self,
        *message_args: Any,
        **error_data: Any,
    ) -> None:
        super().__init__(
            *(message_args or (_UNSUPPORTED_MEDIA_TYPE_DETAIL,)), **error_data
        )

    def response_headers(self) -> dict[str, str]:
        """Return the ``Accept-Patch`` header (RFC 5789 section 2.2)."""
        return {"Accept-Patch": "application/merge-patch+json"}


class InvalidMergePatch(WebError):
    """A merge-patch body is not a JSON object (422).

    The message defaults to ``A merge patch must be a JSON object.``
    """

    def __init__(
        self,
        *message_args: Any,
        **error_data: Any,
    ) -> None:
        super().__init__(
            *(message_args or ("A merge patch must be a JSON object.",)), **error_data
        )


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


class ItemsDenied(PermissionDenied):
    """Some items of a bulk request are not permitted (403).

    Renders ``Forbidden`` with one ``errors`` entry per message, whose
    ``pointer`` is ``/<root>/<index>`` (``/<root>/<index>/<field>`` for a
    field-keyed entry).

    Args:
        errors: Messages by item index, or by item index then field name.
        root: The first pointer segment, such as ``"requests"`` or ``"ids"``.

    Example::

        ItemsDenied({"1": ["You may not create this order."]}, root="requests")
    """

    def __init__(
        self,
        errors: Mapping[str | int, Sequence[str] | Mapping[str, Sequence[str]]],
        *,
        root: str,
    ) -> None:
        super().__init__("Forbidden")
        self.errors = errors
        self.root = root

    def problem_extensions(self) -> Mapping[str, Any]:
        """Return the ``errors`` member."""
        from rn_forge.web.problem import field_error  # noqa: PLC0415  # problem imports this module

        entries: list[dict[str, str]] = []
        for index, item in self.errors.items():
            if isinstance(item, Mapping):
                entries.extend(
                    field_error((self.root, index, field), message)
                    for field, messages in item.items()
                    for message in messages
                )
            else:
                entries.extend(
                    field_error((self.root, index), message) for message in item
                )
        return {"errors": entries}


class RowsInvalid(WebError):
    """One or more rows of an import or bulk request are invalid (422).

    Renders ``One or more rows are invalid.`` with one ``errors`` entry per
    failed cell, whose ``pointer`` is ``/<root>/<row>[/<field>]``.

    Args:
        errors: The failed cells.
        root: The first pointer segment.
    """

    def __init__(self, errors: Iterable[RowError], *, root: str = "rows") -> None:
        super().__init__("One or more rows are invalid.")
        self.errors = tuple(errors)
        self.root = root

    def problem_extensions(self) -> Mapping[str, Any]:
        """Return the ``errors`` member."""
        from rn_forge.web.problem import field_error  # noqa: PLC0415  # problem imports this module

        return {
            "errors": [
                field_error(
                    (self.root, e.row, *([e.field] if e.field else [])), e.message
                )
                for e in self.errors
            ]
        }


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
