"""Standalone Django views that can be included directly from URLconf.

No health-check library is adopted: ``django-health-check`` 4.6.1 (checked 2026-09-23) answers a
failing or warning check with a hard-coded 500, has no required-versus-optional distinction and no
timeout.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Collection, Mapping
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import URLPattern, path
from django.views.decorators.http import require_GET
from rn_forge.web import (
    LEGACY_LIVENESS_PATH,
    LIVENESS_PATH,
    READINESS_PATH,
    Check,
    liveness_body,
    run_checks_sync,
)

from rn_forge.django.utils import RequestUtils

__all__ = [
    "debug_request_view",
    "health_urlpatterns",
    "index_view",
    "liveness_view",
    "readiness_view",
]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@require_GET
def index_view(request: HttpRequest) -> HttpResponse:
    """Render a template-free HTML diagnostics page for the request."""
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
def liveness_view(request: HttpRequest) -> JsonResponse:
    """Return the liveness response, :func:`rn_forge.web.liveness_body` with 200."""
    return JsonResponse(liveness_body())


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

    Returns 503 when a required check fails and 200 otherwise. Async checks are
    rejected by :func:`rn_forge.web.run_checks_sync`.

    Args:
        checks: Name → synchronous check.
        required: Names whose failure makes the service unavailable.
    """

    @require_GET
    def view(request: HttpRequest) -> JsonResponse:
        report = run_checks_sync(checks, required=required)
        return JsonResponse(report.as_body(), status=report.http_status)

    return view


def health_urlpatterns(
    *,
    checks: Mapping[str, Check],
    required: Collection[str] = (),
    timeout: float | None = 2.0,
    liveness_path: str = LIVENESS_PATH,
    readiness_path: str = READINESS_PATH,
    legacy_liveness_path: str | None = LEGACY_LIVENESS_PATH,
) -> list[URLPattern]:
    """Return liveness and readiness URL patterns, with no trailing slash.

    A probe on every host fails on a redirect, so these paths are served
    exactly as configured — a trailing-slash ``APPEND_SLASH`` 301 would mark
    the instance unhealthy.

    Args:
        checks: Name → synchronous readiness check.
        required: Names whose failure makes the service unavailable (503).
        timeout: Seconds each readiness check may run before it is reported
            as ``fail``. ``None`` waits indefinitely.
        liveness_path: The liveness path.
        readiness_path: The readiness path.
        legacy_liveness_path: An alias of *liveness_path*. ``None`` serves no
            alias.
    """

    @require_GET
    def readyz(request: HttpRequest) -> JsonResponse:
        report = run_checks_sync(checks, required=required, timeout=timeout)
        return JsonResponse(report.as_body(), status=report.http_status)

    patterns = [
        path(liveness_path.lstrip("/"), liveness_view, name="rn-forge-liveness"),
        path(readiness_path.lstrip("/"), readyz, name="rn-forge-readiness"),
    ]
    if legacy_liveness_path is not None:
        patterns.append(
            path(
                legacy_liveness_path.lstrip("/"),
                liveness_view,
                name="rn-forge-liveness-legacy",
            )
        )
    return patterns
