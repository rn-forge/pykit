"""Django exception handlers for legacy JSON and RFC 9457 responses."""

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
    PROBLEM_MEDIA_TYPE,
    ProblemRegistry,
    ProblemType,
    default_registry,
    render_problem,
)

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

    Includes the current trace id. A 401 uses a generic detail and adds a
    ``WWW-Authenticate`` challenge unless *headers* already contains one.

    Args:
        exc: The exception being rendered.
        instance: The ``instance`` member — in practice the request path.
        registry: The rows to render with.
        problem: The row to use instead of resolving one from *exc*.
        detail: Overrides the registry's derived detail.
        extensions: Extra members, flattened onto the body.
        headers: Response headers to carry, e.g. a DRF-built challenge.
    """
    rendered = render_problem(
        registry,
        exc,
        instance=instance,
        problem=problem,
        detail=detail,
        extensions=extensions,
        headers=headers,
    )
    if rendered.status >= 500:
        _LOGGER.error(
            "Problem response: status={} instance={}",
            rendered.status,
            instance,
            exc_info=exc,
        )
    response = JsonResponse(
        rendered.body, status=rendered.status, content_type=PROBLEM_MEDIA_TYPE
    )
    for name, value in rendered.headers.items():
        response[name] = value
    return response


def problem_details_handler404(
    request: HttpRequest, exception: Exception | None = None
) -> JsonResponse:
    """Render an unmatched Django route as a problem response."""
    row = _REGISTRY.problem_for_status(HTTPStatus.NOT_FOUND)
    return problem_details_response(
        exception or Resolver404(),
        instance=request.path,
        registry=_REGISTRY,
        problem=row,
        detail=row.title,
    )


def problem_details_handler500(request: HttpRequest) -> JsonResponse:
    """Render an exception escaping a plain Django view as a problem."""
    return problem_details_response(
        RuntimeError("Unhandled exception"),
        instance=request.path,
        registry=_REGISTRY,
    )
