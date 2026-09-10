"""Reusable DRF view mixins for rn-forge-django."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast, override
from datetime import date

from django.http import HttpRequest
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.lang.utils import AppUtils
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rn_forge.django.drf import AuthenticatedRequestUser, RequestUtils
from rn_forge.django.drf._typing import (
    CreateModelMixinProtocol,
    GenericAPIViewProtocol,
    QuerySetProtocol,
    SerializerData,
    SerializerProtocol,
    UpdateModelMixinProtocol,
)
from rn_forge.django.models import DateRangeModel

__all__ = [
    "AuditFieldsViewMixin",
    "ExceptionContextViewMixin",
    "ModelFilterViewMixin",
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
        "bulk_create": "Error creating records.",
        "update": "Error updating record.",
        "partial_update": "Error updating record.",
        "destroy": "Error deleting record.",
        "bulk_delete": "Error deleting records.",
        "export": "Error exporting records.",
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


# ---------------------------------------------------------------------------
# Model Filtering
# ---------------------------------------------------------------------------


class ModelFilterViewMixin:
    """Default queryset filtering for rn-forge model viewsets."""

    filterset_fields: ClassVar[Mapping[str, Sequence[str]]] = {
        "id": ("exact", "in"),
        "status": ("exact", "in"),
        "created_by": ("exact",),
        "created_at": ("gte", "lte"),
        "updated_by": ("exact",),
        "updated_at": ("gte", "lte"),
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
