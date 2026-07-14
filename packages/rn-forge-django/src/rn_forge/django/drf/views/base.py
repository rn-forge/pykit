"""Small generic DRF base views composed from rn-forge-django mixins."""

from rest_framework.generics import GenericAPIView
from rest_framework.viewsets import ModelViewSet
from rn_forge.django.drf.views.bulk import (
    BulkCreateViewMixin,
    BulkDeleteViewMixin,
)
from rn_forge.django.drf.views.mixins import (
    AuditFieldsViewMixin,
    ExceptionContextViewMixin,
    ModelFilterViewMixin,
    RequestAccessViewMixin,
)
from rn_forge.django.drf.views.transfer import (
    BulkLoadImportViewMixin,
    ExportViewMixin,
    SnapshotImportViewMixin,
    UpsertImportViewMixin,
)

__all__ = [
    "BaseAPIView",
    "BaseModelViewSet",
    "BulkLoadImportModelViewSet",
    "ExportModelViewSet",
    "SnapshotImportModelViewSet",
    "UpsertImportModelViewSet",
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
    ModelFilterViewMixin,
    BulkCreateViewMixin,
    BulkDeleteViewMixin,
    ModelViewSet,
):
    """Generic DRF model viewset with request helpers, exceptions, and bulk actions."""


class ExportModelViewSet(
    ExportViewMixin,
    BaseModelViewSet,
):
    """Model viewset base with export transfer actions."""


class UpsertImportModelViewSet(
    UpsertImportViewMixin,
    ExportModelViewSet,
):
    """Model viewset base with upsert import plus export/template actions."""


class SnapshotImportModelViewSet(
    SnapshotImportViewMixin,
    ExportModelViewSet,
):
    """Model viewset base with snapshot import plus export/template actions."""


class BulkLoadImportModelViewSet(
    BulkLoadImportViewMixin,
    ExportModelViewSet,
):
    """Model viewset base with DB-shaped load import plus export/template actions."""
