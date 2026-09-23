"""Simple Django URLconf for reusable helper views."""

from django.urls import path

from rn_forge.django.views import (
    debug_request_view,
    index_view,
)

__all__ = ["urlpatterns"]

urlpatterns = [
    path("", index_view, name="rn-forge-index"),
    path("debug-request/", debug_request_view, name="rn-forge-debug-request"),
]
