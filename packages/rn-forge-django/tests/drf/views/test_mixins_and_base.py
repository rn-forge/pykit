from __future__ import annotations

from typing import ClassVar

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rn_forge.django.drf.views.base import BaseAPIView
from rn_forge.django.drf.views.mixins import (
    ExceptionContextViewMixin,
    PermissionByMethodMixin,
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


def _permission_types(view_class, method: str) -> list[type]:
    view = view_class()
    view.request = Request(APIRequestFactory().generic(method, "/"))
    return [type(permission) for permission in view.get_permissions()]


class TestPermissionByMethodMixin:
    class _Mapped(PermissionByMethodMixin):
        permission_classes: ClassVar = [IsAuthenticated]
        PERMISSION_CLASSES_BY_METHOD: ClassVar = {
            "POST": [IsAdminUser],
            "GET": [AllowAny],
        }

    class _Unmapped(PermissionByMethodMixin):
        permission_classes: ClassVar = [IsAuthenticated]

    def test_mapped_method_uses_its_classes(self) -> None:
        assert _permission_types(self._Mapped, "post") == [IsAdminUser]
        assert _permission_types(self._Mapped, "GET") == [AllowAny]

    def test_unmapped_method_falls_back_to_permission_classes(self) -> None:
        assert _permission_types(self._Mapped, "DELETE") == [IsAuthenticated]

    def test_empty_map_behaves_like_the_plain_view(self) -> None:
        for method in ("GET", "POST", "PATCH"):
            assert _permission_types(self._Unmapped, method) == [IsAuthenticated]
