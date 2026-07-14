from __future__ import annotations

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rest_framework.generics import GenericAPIView  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.views.base import BaseAPIView  # noqa: E402
from rn_forge.django.drf.views.mixins import (  # noqa: E402
    ExceptionContextViewMixin,
    RequestAccessViewMixin,
)

pytestmark = pytest.mark.unit


class _RequestAccessView(RequestAccessViewMixin):
    def __init__(self) -> None:
        self.request = APIRequestFactory().post(
            "/?page=2",
            {"name": "widget", "count": 3},
            format="json",
        )


class _ExceptionView(ExceptionContextViewMixin, GenericAPIView):
    def __init__(self, action: str) -> None:
        self.action = action


class _BaseView(BaseAPIView):
    def __init__(self) -> None:
        self.request = APIRequestFactory().get("/")


class TestRequestAccessViewMixin:
    def test_get_request_param(self) -> None:
        view = _RequestAccessView()
        assert view.get_request_param("page") == "2"

    def test_get_request_data(self) -> None:
        view = _RequestAccessView()
        assert view.get_request_data("name") == "widget"

    def test_get_request_string(self) -> None:
        view = _RequestAccessView()
        assert view.get_request_string("name") == "widget"


class TestExceptionContextViewMixin:
    def test_uses_action_specific_message(self) -> None:
        view = _ExceptionView("create")
        context = view.get_exception_handler_context()
        assert context["message"] == "Error creating record(s)"


class TestBaseAPIView:
    def test_includes_request_access_helpers(self) -> None:
        view = _BaseView()
        assert view.get_request_param("missing", "fallback") == "fallback"
