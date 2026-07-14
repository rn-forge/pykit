"""DRF-specific exception helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from rest_framework import status
from rest_framework.request import Request
from rn_forge.django.exceptions import json_exception_response
from rn_forge.django.drf.utils import RequestUtils

from django.http import JsonResponse

__all__ = [
    "drf_exception_handler",
]


def drf_exception_handler(
    exc: Exception, context: Mapping[str, object]
) -> JsonResponse:
    """Handle DRF exceptions with a normalized JSON response."""
    request = cast(Request, context["request"])
    message = cast(str | None, context.get("message", str(exc)))
    status_code = cast(
        int, getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    )
    return json_exception_response(
        RequestUtils.get_django_request(request),
        str(exc),
        message,
        status_code,
    )
