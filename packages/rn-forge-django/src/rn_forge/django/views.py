"""Standalone Django views that can be included directly from URLconf."""

from __future__ import annotations

import html
import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from rn_forge.django.utils import RequestUtils

__all__ = [
    "debug_request_view",
    "healthcheck_view",
    "index_view",
]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def index_view(request: HttpRequest) -> HttpResponse:
    """Render a minimal HTML diagnostics page for the current request.

    This endpoint is intentionally dependency-light so consuming apps can
    include it directly from URLconf without adding templates.
    """
    payload: dict[str, Any] = {
        "version": getattr(settings, "VERSION", None),
        "request": RequestUtils.debug_request(request),
    }
    pretty = html.escape(json.dumps(payload, indent=2, default=str))
    return HttpResponse(
        (
            "<!doctype html>"
            "<html><head><title>rn-forge-django</title>"
            "<meta charset='utf-8'>"
            "<style>"
            "body{font-family:ui-monospace,monospace;margin:2rem;line-height:1.5;}"
            "h1{font-size:1.25rem;}pre{background:#f5f5f5;padding:1rem;overflow:auto;}"
            "</style>"
            "</head><body>"
            "<h1>rn-forge-django</h1>"
            f"<pre>{pretty}</pre>"
            "</body></html>"
        ).encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )


def healthcheck_view(request: HttpRequest) -> HttpResponse:
    """Return a lightweight liveness response."""
    return HttpResponse(b"healthy", status=200)


def debug_request_view(request: HttpRequest, **kwargs: Any) -> JsonResponse:
    """Return the structured request snapshot produced by :class:`RequestUtils`."""
    return JsonResponse(RequestUtils.debug_request(request), **kwargs)
