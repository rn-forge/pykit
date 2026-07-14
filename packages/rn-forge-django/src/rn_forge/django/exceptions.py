"""Shared exception helpers for Django-level JSON error handling."""

from __future__ import annotations

from http import HTTPStatus
from typing import cast

import django.conf.urls
import django.core.handlers.exception
from django.http import HttpRequest, JsonResponse
from django.urls.exceptions import Resolver404
from rn_forge.commons.logging import AppLogger

__all__ = [
    "django_exception_handler",
    "json_exception_response",
    "register_django_exception_handlers",
]

_LOGGER = AppLogger.get_logger(__name__)


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
