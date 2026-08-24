from __future__ import annotations

import json

import pytest

django = pytest.importorskip("django")

from django.http import HttpRequest  # noqa: E402

from rn_forge.django.views import (  # noqa: E402
    debug_request_view,
    healthcheck_view,
    index_view,
)

pytestmark = pytest.mark.unit


class TestHelperViews:
    def test_healthcheck_view(self) -> None:
        request = HttpRequest()
        request.method = "GET"
        response = healthcheck_view(request)
        assert response.status_code == 200
        assert response.content == b"healthy"

    def test_debug_request_view(self) -> None:
        request = HttpRequest()
        request.path = "/debug/"
        request.path_info = "/debug/"
        request.method = "GET"
        request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80"}
        response = debug_request_view(request)
        assert response.status_code == 200
        assert json.loads(response.content)["path"] == "/debug/"

    def test_index_view_renders_html(self) -> None:
        request = HttpRequest()
        request.path = "/"
        request.path_info = "/"
        request.method = "GET"
        request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80"}
        response = index_view(request)
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]
        assert b"rn-forge-django" in response.content
