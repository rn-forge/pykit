"""Reusable DRF view mixins for rn-forge-django."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast, override
from datetime import date

from django.http import HttpRequest
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.lang.utils import AppUtils
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import BaseParser
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.django.drf import AuthenticatedRequestUser, RequestUtils
from rn_forge.django.drf.casing import MergePatchParser
from rn_forge.django.drf.concurrency import enforce_version, etag_for
from rn_forge.django.drf._typing import (
    CreateModelMixinProtocol,
    GenericAPIViewProtocol,
    QuerySetProtocol,
    SerializerData,
    SerializerProtocol,
    UpdateModelMixinProtocol,
)
from rn_forge.django.models import DateRangeModel
from rn_forge.django.models.concurrency import VersionedModelMixin
from rn_forge.web import (
    MERGE_PATCH_MEDIA_TYPE,
    ETagCodec,
    UnsupportedMediaType,
    merge_representation,
    require_patch_object,
)

__all__ = [
    "AuditFieldsViewMixin",
    "ExceptionContextViewMixin",
    "MergePatchMixin",
    "ModelFilterViewMixin",
    "PermissionByMethodMixin",
    "RequestAccessViewMixin",
]

_LOGGER = AppLogger.get_logger(__name__)


# Request Access
# ---------------------------------------------------------------------------


class RequestAccessViewMixin:
    """View-level façade over :class:`rn_forge.django.drf.utils.RequestUtils`.

    Child views get a concise ``self.get_request_*`` surface while the DRF
    typing boundaries remain centralized in one helper module.
    """

    request: HttpRequest

    @property
    def drf_request(self) -> Request:
        """Return ``self.request`` narrowed to a DRF request."""
        return cast(Request, self.request)

    def get_request_param(self, key: str, default: str | None = None) -> str | None:
        """Return a query parameter or *default_value*."""
        return RequestUtils.get_param(self.drf_request, key, default)

    def get_request_data(self, key: str | None = None, default: Any = None) -> Any:
        """Return request data, or one body value when *key* is provided."""
        data = RequestUtils.get_data(self.drf_request)
        if key is None:
            return data
        return data.get(key, default)

    def get_request_value(self, key: str, default: Any = None) -> Any:
        """Return a request-body value or *default_value*."""
        return RequestUtils.get_value(self.drf_request, key, default)

    def get_request_string(self, key: str, default: str | None = None) -> str | None:
        """Return a query/body value as a string."""
        return RequestUtils.get_string(self.drf_request, key, default)

    def get_request_user(self) -> AuthenticatedRequestUser:
        """Return the current authenticated request user."""
        return RequestUtils.get_request_user(self.drf_request)

    def get_request_auth(self) -> object:
        """Return the current request auth payload."""
        return RequestUtils.get_request_auth(self.drf_request)


class ExceptionContextViewMixin(GenericAPIView):
    """Override DRF exception context with a friendlier action-based message."""

    exception_action_messages: ClassVar[Mapping[str, str]] = {
        "list": "Error listing records.",
        "retrieve": "Error retrieving record.",
        "create": "Error creating record(s)",
        "batch_get": "Error retrieving records.",
        "batch_create": "Error creating records.",
        "batch_update": "Error updating records.",
        "update": "Error updating record.",
        "partial_update": "Error updating record.",
        "destroy": "Error deleting record.",
        "batch_delete": "Error deleting records.",
        "import_items": "Error importing records.",
        "import_template": "Error building import template.",
    }

    @override
    def get_exception_handler_context(self) -> dict[str, Any]:
        context = cast(dict[str, Any], super().get_exception_handler_context())
        action = str(getattr(self, "action", ""))
        message = self.exception_action_messages.get(action)
        if message is not None:
            context["message"] = message
        return context


class PermissionByMethodMixin(GenericAPIView):
    """Select DRF permission classes per HTTP method.

    Unmapped methods use the view's ``permission_classes``. An explicitly empty
    sequence leaves that method unguarded.
    """

    PERMISSION_CLASSES_BY_METHOD: ClassVar[
        Mapping[str, Sequence[type[BasePermission]]]
    ] = {}

    @override
    def get_permissions(self) -> Sequence[BasePermission]:  # pyright: ignore[reportIncompatibleMethodOverride]  # DRF stubs return list[BasePermission]
        method = str(self.request.method).upper()
        classes = self.PERMISSION_CLASSES_BY_METHOD.get(method)
        if classes is None:
            return cast(Sequence[BasePermission], super().get_permissions())
        return [permission() for permission in classes]


# ---------------------------------------------------------------------------
# Model Filtering
# ---------------------------------------------------------------------------


class ModelFilterViewMixin:
    """Default queryset filtering for rn-forge model viewsets."""

    filterset_fields: ClassVar[Mapping[str, Sequence[str]]] = {
        "id": ("exact", "in"),
        "status": ("exact", "in"),
        "created_by": ("exact",),
        "create_time": ("gte", "lte"),
        "updated_by": ("exact",),
        "update_time": ("gte", "lte"),
    }
    date_range_active_param = "active"

    def filter_queryset(self, queryset: QuerySetProtocol) -> QuerySetProtocol:
        """Apply parent filters plus rn-forge's date-range active filter."""
        view = cast(GenericAPIViewProtocol, super())
        filtered = view.filter_queryset(queryset)
        if not self._should_filter_active_date_range(filtered):
            return filtered

        today = date.today()
        _LOGGER.debug(
            "Applying active date-range filter: model={} date={}", filtered.model, today
        )
        return filtered.filter(start_date__lte=today).exclude(end_date__lte=today)

    def _should_filter_active_date_range(self, queryset: QuerySetProtocol) -> bool:
        """Return whether the request asks for active date-range filtering."""
        model = queryset.model
        if not issubclass(model, DateRangeModel):
            return False
        value = cast(RequestAccessViewMixin, self).get_request_param(
            self.date_range_active_param
        )
        return AppUtils.parse_bool(value, strict=False) is True


# ---------------------------------------------------------------------------
# Audit Fields
# ---------------------------------------------------------------------------


class AuditFieldsViewMixin(RequestAccessViewMixin):
    """Populate common audit fields before model serializer saves."""

    def get_audit_user_identifier(self) -> str:
        """Return the actor identifier used for create/update audit fields."""
        user = self.get_request_user()
        return user.email if user.is_authenticated else "anonymous"

    def prepare_create_data(self, validated_data: SerializerData) -> SerializerData:
        """Populate create audit fields on one validated serializer row."""
        audit_identifier = self.get_audit_user_identifier()
        validated_data["created_by"] = audit_identifier
        validated_data["updated_by"] = audit_identifier
        return validated_data

    def prepare_update_data(self, validated_data: SerializerData) -> SerializerData:
        """Populate update audit fields on one validated serializer row."""
        validated_data.pop("created_by", None)
        validated_data["updated_by"] = self.get_audit_user_identifier()
        return validated_data

    def perform_create(self, serializer: SerializerProtocol) -> None:
        """Populate audit fields before DRF persists a new model instance."""
        self.prepare_create_data(serializer.validated_data)
        _LOGGER.debug(
            "Preparing create audit fields: actor={}", self.get_audit_user_identifier()
        )
        cast(CreateModelMixinProtocol, super()).perform_create(serializer)

    def perform_update(self, serializer: SerializerProtocol) -> None:
        """Populate update audit fields before DRF persists an existing model instance."""
        self.prepare_update_data(serializer.validated_data)
        _LOGGER.debug(
            "Preparing update audit fields: actor={}", self.get_audit_user_identifier()
        )
        cast(UpdateModelMixinProtocol, super()).perform_update(serializer)


# ---------------------------------------------------------------------------
# JSON Merge Patch
# ---------------------------------------------------------------------------


class MergePatchMixin(GenericAPIView):
    """``PATCH`` as an RFC 7396 JSON Merge Patch, for a viewset's ``partial_update``.

    ``PATCH`` accepts only ``application/merge-patch+json``; any other media
    type is a 415. ``PUT`` and ``POST`` keep the view's own parsers. The
    current representation is merged with the patch and the result validated
    as a full update.
    A top-level ``null`` sets that field to ``null``; read-only and unknown
    members are ignored.

    When the instance is a :class:`~rn_forge.django.models.VersionedModelMixin`,
    ``If-Match`` is enforced and ``retrieve`` and ``PATCH`` answer with an ``ETag``.

    Attributes:
        merge_patch_requires_if_match: When ``True``, a versioned ``PATCH``
            without a precondition is a 428.
        etag_codec: The validator format; ``None`` uses
            :class:`rn_forge.web.VersionETagCodec`.
    """

    merge_patch_requires_if_match: ClassVar[bool] = False
    etag_codec: ClassVar[ETagCodec | None] = None

    @override
    def get_parsers(self) -> list[BaseParser]:
        # DRF builds the request (and so the parsers) before a view's own `request` is set.
        method = getattr(getattr(self, "request", None), "method", None)
        if str(method).upper() == "PATCH":
            return [MergePatchParser()]
        return cast(list[BaseParser], super().get_parsers())

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the instance, with an ``ETag`` when it is versioned."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, headers=self._etag_headers(instance))

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Apply a merge patch.

        Raises:
            rn_forge.web.UnsupportedMediaType: The media type is not
                ``application/merge-patch+json`` (415).
            rn_forge.web.PreconditionRequired: A required ``If-Match`` is
                missing (428).
            rn_forge.web.MalformedPrecondition: ``If-Match`` is unparseable (400).
            rn_forge.web.VersionConflict: ``If-Match`` is stale (412).
            rn_forge.web.InvalidMergePatch: The body is not a JSON object (422).
            rest_framework.exceptions.ValidationError: The merged document is
                invalid (422).
        """
        media_type = str(request.content_type).split(";", 1)[0].strip().lower()
        if media_type != MERGE_PATCH_MEDIA_TYPE:
            raise UnsupportedMediaType()
        instance = self.get_object()
        if isinstance(instance, VersionedModelMixin):
            enforce_version(
                request,
                instance,
                required=self.merge_patch_requires_if_match,
                codec=self.etag_codec,
            )
        patch = require_patch_object(cast(object, request.data))  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data partially untyped
        current = cast(Mapping[str, Any], self.get_serializer(instance).data)
        serializer = self.get_serializer(
            instance, data=merge_representation(current, patch)
        )
        serializer.is_valid(raise_exception=True)
        cast(UpdateModelMixinProtocol, self).perform_update(serializer)
        return Response(serializer.data, headers=self._etag_headers(instance))

    def _etag_headers(self, instance: object) -> dict[str, str]:
        if not isinstance(instance, VersionedModelMixin):
            return {}
        return {"ETag": etag_for(instance, codec=self.etag_codec)}
