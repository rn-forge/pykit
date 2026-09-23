from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory
import pytest

from rn_forge.django.security import SECURITY_SETTINGS, SecurityHeadersMiddleware

pytestmark = pytest.mark.unit


def test_cache_control_and_csp_are_stamped() -> None:
    def view(request):
        return HttpResponse(status=200)

    response = SecurityHeadersMiddleware(view)(RequestFactory().get("/x"))
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Security-Policy"] == "frame-ancestors 'none'"


def test_a_view_that_already_set_either_header_wins() -> None:
    def view(request):
        response = HttpResponse(status=200)
        response["Cache-Control"] = "public, max-age=3600"
        return response

    response = SecurityHeadersMiddleware(view)(RequestFactory().get("/x"))
    assert response["Cache-Control"] == "public, max-age=3600"
    assert response["Content-Security-Policy"] == "frame-ancestors 'none'"


def test_security_settings_has_hsts_off_by_default() -> None:
    assert SECURITY_SETTINGS["SECURE_HSTS_SECONDS"] == 0
    assert SECURITY_SETTINGS["X_FRAME_OPTIONS"] == "DENY"
    assert SECURITY_SETTINGS["SECURE_REFERRER_POLICY"] == "no-referrer"
    assert SECURITY_SETTINGS["SECURE_CONTENT_TYPE_NOSNIFF"] is True
