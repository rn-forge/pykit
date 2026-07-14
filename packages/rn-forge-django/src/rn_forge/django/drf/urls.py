"""DRF URLconf for reusable API views."""

from typing import Any, cast

from django.urls import path

from rn_forge.django.drf.views.enums import EnumChoicesAPIView

__all__ = ["urlpatterns"]

enum_choices_view = cast(Any, EnumChoicesAPIView).as_view()

urlpatterns = [
    path(
        "enums/<str:app>/<str:enum>/",
        enum_choices_view,
        name="rn-forge-enum-choices",
    ),
]
