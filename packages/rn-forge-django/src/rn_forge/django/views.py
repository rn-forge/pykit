"""Standalone Django views that can be included directly from URLconf."""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Collection, Mapping
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from rn_forge.web import Check, run_checks_sync

from rn_forge.django.utils import RequestUtils

__all__ = [
    "debug_request_view",
    "healthcheck_view",
    "index_view",
    "readiness_view",
]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@require_GET
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


@require_GET
def healthcheck_view(request: HttpRequest) -> HttpResponse:
    """Return a lightweight liveness response."""
    return HttpResponse(b"healthy", status=200)


@require_GET
def debug_request_view(request: HttpRequest, **kwargs: Any) -> JsonResponse:
    """Return the structured request snapshot produced by :class:`RequestUtils`."""
    return JsonResponse(RequestUtils.debug_request(request), **kwargs)


def readiness_view(
    checks: Mapping[str, Check],
    *,
    required: Collection[str] = (),
) -> Callable[[HttpRequest], JsonResponse]:
    """Build a readiness view that reports one entry per dependency check.

    A factory, so the checks are the URLconf's to supply::

        path("readyz", readiness_view({"database": ping_db}, required=["database"]))

    The body is :meth:`rn_forge.web.HealthReport.as_body` and the status is the
    report's own: 503 when a check named in *required* fails, 200 otherwise.
    Every semantic — exception capture, ``bool`` coercion, the four statuses —
    is :func:`rn_forge.web.run_checks_sync`'s, which also raises on an async
    check rather than report it as passing. Liveness is
    :func:`healthcheck_view`, which runs nothing.

    Args:
        checks: Name → synchronous check.
        required: Names whose failure makes the service unavailable.
    """

    @require_GET
    def view(request: HttpRequest) -> JsonResponse:
        report = run_checks_sync(checks, required=required)
        return JsonResponse(report.as_body(), status=report.http_status)

    return view
