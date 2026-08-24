from __future__ import annotations

import json

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from django.http import HttpRequest  # noqa: E402
from django.urls.exceptions import Resolver404  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.exceptions import drf_exception_handler  # noqa: E402
from rn_forge.django.exceptions import (  # noqa: E402
    django_exception_handler,
    json_exception_response,
)

pytestmark = pytest.mark.unit


class TestJsonExceptionResponse:
    def test_builds_json_response_for_http_request(self) -> None:
        request = HttpRequest()
        request.path = "/widgets/"

        response = json_exception_response(
            request,
            "ValidationError",
            "bad payload",
            400,
        )

        assert response.status_code == 400
        assert json.loads(response.content) == {
            "path": "/widgets/",
            "error": "ValidationError",
            "message": "bad payload",
        }


class TestDjangoExceptionHandler:
    def test_maps_resolver404(self) -> None:
        request = HttpRequest()
        request.path = "/missing/"

        response = django_exception_handler(request, Resolver404())

        assert response.status_code == 404
        assert json.loads(response.content)["error"] == "Path Not Found"


class TestDrfExceptionHandler:
    def test_uses_context_message(self) -> None:
        request = Request(APIRequestFactory().get("/widgets/"))  # pyright: ignore[reportArgumentType]
        exc = RuntimeError("boom")

        response = drf_exception_handler(
            exc,
            {
                "request": request,
                "message": "custom message",
            },
        )

        assert response.status_code == 500
        assert json.loads(response.content) == {
            "path": "/widgets/",
            "error": "boom",
            "message": "custom message",
        }
