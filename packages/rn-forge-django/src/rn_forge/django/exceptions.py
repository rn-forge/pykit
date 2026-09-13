"""Shared exception helpers for Django-level JSON error handling.

Two families live here:

- :func:`json_exception_response` / :func:`django_exception_handler` — this
  package's original ``{"path", "error", "message"}`` body. Unchanged.
- :func:`problem_details_response` and the ``handler404``/``handler500`` views
  over it — RFC 9457 ``application/problem+json`` bodies built by
  :class:`rn_forge.web.ProblemRegistry`, the shape every ``rn-forge-*``
  application returns. The DRF exception handler
  :func:`rn_forge.django.drf.exceptions.problem_details_exception_handler`
  renders through the same function, so a routing 404 and a view's 404 cannot
  differ.

Nothing here decides a slug, a status or a detail; the registry does.
"""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Final, cast

import django.conf.urls
import django.core.handlers.exception
from django.http import HttpRequest, JsonResponse
from django.urls.exceptions import Resolver404
from rn_forge.commons.logging import AppLogger
from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    PROBLEM_MEDIA_TYPE,
    ProblemRegistry,
    ProblemType,
    challenge_header,
    default_registry,
    get_correlation_id,
)
from rn_forge.web.context import CORRELATION_ID_KEY

__all__ = [
    "django_exception_handler",
    "json_exception_response",
    "problem_details_handler404",
    "problem_details_handler500",
    "problem_details_response",
    "register_django_exception_handlers",
]

_LOGGER = AppLogger.get_logger(__name__)
_REGISTRY: Final = default_registry()


def json_exception_response(
    request: HttpRequest,
    error: str,
    message: str | None,
    status_code: int,
) -> JsonResponse:
    """Build a normalized JSON response for handled exceptions."""
    final_message = message or "An error occurred"
    _LOGGER.exception(
        "Django exception response: path={} message={}", request.path, final_message
    )
    return JsonResponse(
        {
            "path": request.path,
            "error": error,
            "message": final_message,
        },
        status=status_code,
    )


def django_exception_handler(
    request: HttpRequest,
    *args: object,
    **kwargs: object,
) -> JsonResponse:
    """Handle plain Django exceptions with a normalized JSON response."""
    exception = cast(
        object | None,
        kwargs.get("exception", args[0] if args else None),
    )
    if isinstance(exception, Resolver404):
        error = "Path Not Found"
        status_code = HTTPStatus.NOT_FOUND
    else:
        error = "Internal Server Error"
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    return json_exception_response(
        request,
        error,
        cast(str | None, kwargs.get("message")),
        status_code,
    )


def register_django_exception_handlers() -> None:
    """Register :func:`django_exception_handler` as the global Django handler."""
    django.conf.urls.handler400 = django_exception_handler
    django.conf.urls.handler403 = django_exception_handler
    django.conf.urls.handler404 = django_exception_handler
    django.conf.urls.handler500 = django_exception_handler
    django.core.handlers.exception.response_for_exception = django_exception_handler


def problem_details_response(
    exc: BaseException,
    *,
    instance: str,
    registry: ProblemRegistry,
    problem: ProblemType | None = None,
    detail: str | None = None,
    extensions: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JsonResponse:
    """Render *exc* as an ``application/problem+json`` response.

    The bound correlation ID is always attached as the ``correlation_id``
    extension (``null`` when no middleware bound one). A 401 says only that
    authentication failed and carries a ``WWW-Authenticate`` challenge — one
    built by :func:`rn_forge.web.challenge_header` unless *headers* already
    has one. A 5xx is logged with its traceback, since the body says nothing.

    Args:
        exc: The exception being rendered.
        instance: The ``instance`` member — in practice the request path.
        registry: The rows to render with.
        problem: The row to use instead of resolving one from *exc*.
        detail: Overrides the registry's derived detail.
        extensions: Extra members, flattened onto the body.
        headers: Response headers to carry, e.g. a DRF-built challenge.
    """
    row = problem if problem is not None else registry.problem_for(exc)
    body = registry.build(
        exc,
        instance=instance,
        detail=AUTH_FAILED_DETAIL if row.status == 401 else detail,
        problem=row,
        extensions={CORRELATION_ID_KEY: get_correlation_id(), **(extensions or {})},
    )
    if row.status >= 500:
        _LOGGER.error(
            "Problem response: status={} instance={}",
            row.status,
            instance,
            exc_info=exc,
        )
    response = JsonResponse(
        body.as_body(), status=body.status, content_type=PROBLEM_MEDIA_TYPE
    )
    for name, value in (headers or {}).items():
        response[name] = value
    if row.status == 401 and not response.has_header("WWW-Authenticate"):
        response["WWW-Authenticate"] = challenge_header()
    return response


def problem_details_handler404(
    request: HttpRequest, exception: Exception | None = None
) -> JsonResponse:
    """Render Django's own 404 — an unmatched route — as a problem.

    Name it from the root URLconf:
    ``handler404 = "rn_forge.django.exceptions.problem_details_handler404"``.
    """
    row = _REGISTRY.problem_for_status(HTTPStatus.NOT_FOUND)
    return problem_details_response(
        exception or Resolver404(),
        instance=request.path,
        registry=_REGISTRY,
        problem=row,
        detail=row.title,
    )


def problem_details_handler500(request: HttpRequest) -> JsonResponse:
    """Render an exception escaping a plain Django view as a problem.

    Name it from the root URLconf:
    ``handler500 = "rn_forge.django.exceptions.problem_details_handler500"``.
    DRF views never reach it; their exceptions go through the DRF handler.
    """
    return problem_details_response(
        RuntimeError("Unhandled exception"),
        instance=request.path,
        registry=_REGISTRY,
    )
