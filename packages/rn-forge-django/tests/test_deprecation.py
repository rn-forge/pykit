from __future__ import annotations

from datetime import UTC, datetime

from django.http import HttpResponse
from django.test import RequestFactory
import pytest

from rn_forge.django.deprecation import deprecated

pytestmark = pytest.mark.unit

DEPRECATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET = datetime(2026, 7, 1, tzinfo=UTC)


def test_the_response_carries_the_deprecation_headers() -> None:
    @deprecated(
        deprecated_at=DEPRECATED_AT,
        sunset=SUNSET,
        link="https://example.com/deprecated",
    )
    def view(request):
        return HttpResponse(status=200)

    response = view(RequestFactory().get("/x"))
    assert response["Deprecation"] == "@1767225600"
    assert response["Sunset"] == "Wed, 01 Jul 2026 00:00:00 GMT"
    assert response["Link"] == '<https://example.com/deprecated>; rel="deprecation"'


def test_no_sunset_or_link_omits_those_headers() -> None:
    @deprecated(deprecated_at=DEPRECATED_AT)
    def view(request):
        return HttpResponse(status=200)

    response = view(RequestFactory().get("/x"))
    assert response["Deprecation"] == "@1767225600"
    assert "Sunset" not in response
    assert "Link" not in response
