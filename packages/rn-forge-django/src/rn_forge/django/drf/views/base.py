"""Small generic DRF base views composed from rn-forge-django mixins."""

from rest_framework.generics import GenericAPIView
from rest_framework.viewsets import ModelViewSet
from rn_forge.django.drf.views.mixins import (
    AuditFieldsViewMixin,
    ExceptionContextViewMixin,
    MergePatchMixin,
    ModelFilterViewMixin,
    ReadMaskMixin,
    RequestAccessViewMixin,
)

__all__ = [
    "BaseAPIView",
    "BaseModelViewSet",
]


class BaseAPIView(
    RequestAccessViewMixin,
    ExceptionContextViewMixin,
    GenericAPIView,
):
    """Generic DRF base view with request helpers and exception context."""


class BaseModelViewSet(
    AuditFieldsViewMixin,
    ExceptionContextViewMixin,
    MergePatchMixin,
    ModelFilterViewMixin,
    ReadMaskMixin,
    ModelViewSet,
):
    """Generic DRF model viewset with request helpers, exception context, merge-patch ``PATCH`` and ``readMask``."""
