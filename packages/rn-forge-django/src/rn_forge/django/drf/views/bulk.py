"""Bulk DRF view mixins for serializer-driven create/delete flows."""

from __future__ import annotations

from typing import Any, cast

from rest_framework import status
from rest_framework.decorators import action  # pyright: ignore[reportUnknownVariableType]
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.logging import AppLogger
from rn_forge.django.drf.utils import RequestUtils
from rn_forge.django.drf._typing import (
    ListSerializerProtocol,
    ModelViewSetProtocol,
    RequestProtocol,
    SerializerData,
)
from rn_forge.django.drf.views.mixins import AuditFieldsViewMixin

from django.db import transaction

__all__ = [
    "BulkCreateViewMixin",
    "BulkDeleteViewMixin",
]

bulk_action = cast(Any, action)
_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class BulkCreateViewMixin:
    """Add a ``bulk_create`` action backed by the view serializer."""

    def prepare_bulk_create_item(self, item: SerializerData) -> SerializerData:
        """Return one request payload item before serializer validation."""
        return item

    def validate_bulk_create_item(self, item: SerializerData) -> str | None:
        """Return an error string for one validated item, or ``None``."""
        return None

    @bulk_action(methods=["post"], detail=False, url_path="bulk-create")
    def bulk_create(
        self: ModelViewSetProtocol,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        items = cast(RequestProtocol, request).data
        if not isinstance(items, list):
            _LOGGER.warning("Bulk create rejected: request data is not a list")
            return Response(
                {"message": "Request data must be a list of objects"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item_list = cast(list[object], items)
        _LOGGER.notice(
            "Bulk create started: path={} count={}", request.path, len(item_list)
        )
        mixin = cast(BulkCreateViewMixin, self)
        prepared_items = [
            mixin.prepare_bulk_create_item(cast(SerializerData, item))
            for item in item_list
        ]

        serializer = cast(
            ListSerializerProtocol,
            self.get_serializer(data=prepared_items, many=True),
        )
        serializer.is_valid(raise_exception=True)

        errors: list[str] = []
        for item in serializer.validated_data:
            if isinstance(self, AuditFieldsViewMixin):
                self.prepare_create_data(item)
            error = mixin.validate_bulk_create_item(item)
            if error is not None:
                errors.append(error)

        if errors:
            _LOGGER.warning(
                "Bulk create permission/validation errors: count={}", len(errors)
            )
            self.permission_denied(
                request,
                message="\n".join(errors),
                code="PermissionDenied",
            )

        with cast(Any, transaction).atomic():
            serializer.save()

        _LOGGER.success("Bulk create completed: count={}", len(prepared_items))
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )


class BulkDeleteViewMixin:
    """Add a ``bulk_delete`` action for deleting by primary-key list."""

    bulk_delete_ids_key = "ids"

    def validate_bulk_delete_instance(self, instance: Any) -> str | None:
        """Return an error string for one delete target, or ``None``."""
        return None

    @bulk_action(methods=["delete"], detail=False, url_path="bulk-delete")
    def bulk_delete(
        self: ModelViewSetProtocol,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        mixin = cast(BulkDeleteViewMixin, self)
        ids = RequestUtils.get_value(request, mixin.bulk_delete_ids_key, [])
        if not ids:
            _LOGGER.warning("Bulk delete rejected: no ids provided")
            return Response(
                {"message": "No IDs provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _LOGGER.notice("Bulk delete started: path={} count={}", request.path, len(ids))
        allowed: list[Any] = []
        errors: list[str] = []
        queryset = self.filter_queryset(self.get_queryset()).filter(pk__in=ids)
        for instance in queryset:
            error = mixin.validate_bulk_delete_instance(instance)
            if error is None:
                allowed.append(instance)
            else:
                errors.append(error)

        if errors:
            _LOGGER.warning(
                "Bulk delete permission/validation errors: count={}", len(errors)
            )
            self.permission_denied(
                request,
                message="\n".join(errors),
                code="PermissionDenied",
            )

        with cast(Any, transaction).atomic():
            for instance in allowed:
                instance.delete()

        _LOGGER.success("Bulk delete completed: count={}", len(allowed))
        return Response(status=status.HTTP_204_NO_CONTENT)
