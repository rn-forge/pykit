from __future__ import annotations

from types import SimpleNamespace

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.views.enums import EnumChoicesAPIView  # noqa: E402
from rn_forge.django.models import BaseEnum  # noqa: E402

pytestmark = pytest.mark.unit


class _SampleEnum(BaseEnum):
    Alpha = "A"
    Beta = "B"


class TestEnumChoicesAPIView:
    def test_returns_choices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        view = EnumChoicesAPIView.as_view()
        request = APIRequestFactory().get("/enums/demo/SampleEnum/")
        monkeypatch.setattr(
            "rn_forge.django.drf.views.enums.apps.get_app_config",
            lambda _label: SimpleNamespace(
                models_module=SimpleNamespace(SampleEnum=_SampleEnum)
            ),
        )

        response = view(request, app="demo", enum="SampleEnum")

        assert response.status_code == 200
        assert response.data == [
            {"code": "A", "name": "Alpha"},
            {"code": "B", "name": "Beta"},
        ]

    def test_applies_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        view = EnumChoicesAPIView.as_view()
        request = APIRequestFactory().get("/enums/demo/SampleEnum/?codes=B")
        monkeypatch.setattr(
            "rn_forge.django.drf.views.enums.apps.get_app_config",
            lambda _label: SimpleNamespace(
                models_module=SimpleNamespace(SampleEnum=_SampleEnum)
            ),
        )

        response = view(request, app="demo", enum="SampleEnum")

        assert response.status_code == 200
        assert response.data == [{"code": "B", "name": "Beta"}]
