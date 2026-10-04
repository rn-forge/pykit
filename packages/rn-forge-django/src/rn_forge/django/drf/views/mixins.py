"""Reusable DRF view mixins for rn-forge-django."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast, override
from datetime import date

from django.http import HttpRequest
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.lang.utils import AppUtils
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.serializers import ListSerializer, Serializer
from rest_framework.parsers import BaseParser
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.django.drf import AuthenticatedRequestUser, RequestUtils
from rn_forge.django.drf.casing import MergePatchParser, camelize_key
from rn_forge.django.drf.concurrency import enforce_version, etag_for
from rn_forge.django.drf._typing import (
    action,
    CreateModelMixinProtocol,
    GenericAPIViewProtocol,
    QuerySetProtocol,
    SerializerData,
    SerializerProtocol,
    UpdateModelMixinProtocol,
)
from rn_forge.django.models import DateRangeModel
from rn_forge.django.models.concurrency import VersionedModelMixin
from rn_forge.django.models.soft_delete import SoftDeleteModelMixin
from rn_forge.web import (
    MERGE_PATCH_MEDIA_TYPE,
    READ_MASK_PARAM,
    SHOW_DELETED_PARAM,
    ETagCodec,
    FieldTree,
    ReadMask,
    ResourceNotDeleted,
    UnsupportedMediaType,
    merge_representation,
    parse_flag,
    parse_read_mask,
    require_live,
    require_patch_object,
)

__all__ = [
    "AuditFieldsViewMixin",
    "ExceptionContextViewMixin",
    "MergePatchMixin",
    "ModelFilterViewMixin",
    "PermissionByMethodMixin",
    "ReadMaskMixin",
    "RequestAccessViewMixin",
    "SoftDeleteMixin",
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
        "undelete": "Error undeleting record.",
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


# Partial responses
# ---------------------------------------------------------------------------


def _snake_tree(serializer: Any) -> dict[str, Any]:
    """The readable fields of *serializer* by field name; a nested serializer is a subtree."""
    tree: dict[str, Any] = {}
    for name, field in cast(Mapping[str, Any], serializer.fields).items():
        if field.write_only:
            continue
        nested: Any = (
            cast(Any, field).child if isinstance(field, ListSerializer) else field
        )
        tree[name] = _snake_tree(nested) if isinstance(nested, Serializer) else None
    return tree


def _wire_tree(tree: Mapping[str, Any]) -> FieldTree:
    return {
        camelize_key(name): None if sub is None else _wire_tree(sub)
        for name, sub in tree.items()
    }


def _snake_mask(mask: Mapping[str, Any], declared: Mapping[str, Any]) -> dict[str, Any]:
    """Re-key a mask tree from wire names back to the field names it was parsed against."""
    names = {camelize_key(name): name for name in declared}
    return {
        names[wire]: None if sub is None else _snake_mask(sub, declared[names[wire]])
        for wire, sub in mask.items()
    }


class ReadMaskMixin(GenericAPIView):
    """Honour ``readMask`` on ``retrieve``, ``list`` and ``batch_get``.

    A ``200`` response then holds only the fields the mask names, with its
    ``ETag`` unchanged. On ``list`` the mask applies to each of ``items``, and
    on ``batch_get`` to each resource. Other actions, and responses with any
    other status, are left alone. Fields are selected by their camelCase wire
    names, as declared by the view's serializer; a write-only field is not
    selectable.

    Attributes:
        read_mask_actions: The actions the mask applies to.

    Raises:
        rn_forge.web.InvalidReadMask: The mask combines ``*`` with other paths,
            or a path names no field the serializer declares (400).
    """

    read_mask_actions: ClassVar[frozenset[str]] = frozenset(
        {"retrieve", "list", "batch_get"}
    )

    _read_mask: ReadMask | None = None

    @override
    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        cast(Any, super()).initial(request, *args, **kwargs)
        view: Any = self
        if view.action not in self.read_mask_actions:
            return
        declared = _snake_tree(view.get_serializer())
        mask = parse_read_mask(
            request.query_params.get(READ_MASK_PARAM), fields=_wire_tree(declared)
        )
        if mask is not None:
            self._read_mask = ReadMask(_snake_mask(mask.tree, declared))

    @override
    def finalize_response(
        self, request: Request, response: Any, *args: Any, **kwargs: Any
    ) -> Any:
        response = cast(Any, super()).finalize_response(
            request, response, *args, **kwargs
        )
        if self._read_mask is not None and response.status_code == 200:
            response.data = self._masked(self._read_mask, response.data)
        return response

    def _masked(self, mask: ReadMask, data: Any) -> Any:
        """Apply *mask* to the resources in a ``200`` body of this view's action."""
        if isinstance(data, list):
            return [mask.apply(item) for item in cast(list[Any], data)]
        body = cast(Mapping[str, Any], data)
        action: str = cast(Any, self).action
        if action == "retrieve":
            return mask.apply(body)
        members = {"items"} if action == "list" else set(body)
        return {
            name: self._masked(mask, value) if name in members else value
            for name, value in body.items()
        }


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


class SoftDeleteMixin(GenericAPIView):
    """Soft delete in AIP-164's shape for a viewset over a soft-deleting model.

    The model uses :class:`~rn_forge.django.models.SoftDeleteModelMixin`. List
    this mixin before :class:`~rn_forge.django.drf.views.base.BaseModelViewSet`,
    which supplies the audit actor and the ``ETag`` codec.

    - ``list`` and ``batch_delete`` omit deleted rows; ``list`` includes them
      when ``showDeleted`` is ``true`` or ``1``. Every other action sees all rows.
    - ``DELETE`` soft-deletes and answers 200 with the resource and its ``ETag``.
      A resource that is already deleted is a 404.
    - ``POST {id}:undelete`` restores the resource and answers 200 with it.
    - ``PUT`` and ``PATCH`` on a deleted resource are a 409.

    A versioned instance honours ``If-Match`` on ``DELETE`` and ``:undelete``,
    after the checks above.

    Attributes:
        soft_delete_requires_if_match: When ``True``, a versioned ``DELETE`` or
            ``:undelete`` without a precondition is a 428.

    Raises:
        rest_framework.exceptions.NotFound: ``DELETE`` of a deleted resource (404).
        rn_forge.web.ResourceDeleted: ``PUT`` or ``PATCH`` of a deleted resource (409).
        rn_forge.web.ResourceNotDeleted: ``:undelete`` of a live resource (409).
        rn_forge.web.PreconditionRequired: A required ``If-Match`` is missing (428).
        rn_forge.web.MalformedPrecondition: ``If-Match`` is unparseable (400).
        rn_forge.web.VersionConflict: ``If-Match`` is stale (412).
    """

    soft_delete_requires_if_match: ClassVar[bool] = False

    @override
    def get_queryset(self) -> Any:
        queryset = cast(Any, super().get_queryset())
        action_name = getattr(self, "action", None)
        if action_name == "batch_delete" or (
            action_name == "list"
            and not parse_flag(
                cast(Request, self.request).query_params.get(SHOW_DELETED_PARAM)
            )
        ):
            return queryset.filter(delete_time__isnull=True)
        return queryset

    @override
    def get_object(self) -> Any:
        instance = cast(Any, super().get_object())
        if getattr(self, "action", None) in {"update", "partial_update"}:
            require_live(instance.delete_time, label=_label(instance), id=instance.pk)
        return instance

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Soft-delete the instance and answer with it."""
        instance = self.get_object()
        if instance.delete_time is not None:
            raise NotFound(f"{_label(instance)} {instance.pk} not found")
        self._enforce_precondition(request, instance)
        cast(Any, self).perform_destroy(instance)
        return self._resource_response(instance)

    def perform_destroy(self, instance: SoftDeleteModelMixin) -> None:
        """Soft-delete *instance* as the request's actor."""
        actor = cast(AuditFieldsViewMixin, self).get_audit_user_identifier()
        instance.soft_delete(actor=actor)

    @action(detail=True, methods=["post"], url_path="undelete", url_name="undelete")
    def undelete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Restore a soft-deleted instance and answer with it."""
        instance = self.get_object()
        if instance.delete_time is None:
            raise ResourceNotDeleted(_label(instance), instance.pk)
        self._enforce_precondition(request, instance)
        actor = cast(AuditFieldsViewMixin, self).get_audit_user_identifier()
        instance.undelete(actor=actor)
        return self._resource_response(instance)

    def _enforce_precondition(self, request: Request, instance: Any) -> None:
        if isinstance(instance, VersionedModelMixin):
            enforce_version(
                request,
                instance,
                required=self.soft_delete_requires_if_match,
                codec=cast(ETagCodec | None, getattr(self, "etag_codec", None)),
            )

    def _resource_response(self, instance: Any) -> Response:
        headers: dict[str, str] = {}
        if isinstance(instance, VersionedModelMixin):
            codec = cast(ETagCodec | None, getattr(self, "etag_codec", None))
            headers["ETag"] = etag_for(instance, codec=codec)
        return Response(cast(Any, self).get_serializer(instance).data, headers=headers)


def _label(instance: Any) -> str:
    return str(instance._meta.verbose_name).capitalize()
