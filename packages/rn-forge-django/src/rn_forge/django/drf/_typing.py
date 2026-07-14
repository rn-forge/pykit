"""Internal typing helpers for DRF integration boundaries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Protocol, TypeAlias

from django.http import HttpRequest
from rest_framework.request import Request

__all__ = [
    "BaseSerializerProtocol",
    "ChoiceFieldProtocol",
    "CreateModelMixinProtocol",
    "GenericAPIViewProtocol",
    "ListSerializerProtocol",
    "ModelViewSetProtocol",
    "PrimaryKeyRelatedFieldProtocol",
    "QuerySetProtocol",
    "RequestProtocol",
    "SerializerData",
    "SerializerProtocol",
    "UpdateModelMixinProtocol",
]

SerializerData: TypeAlias = dict[str, Any]


class RequestProtocol(Protocol):
    """Typed proxy for ``rest_framework.request.Request`` attributes."""

    _request: HttpRequest
    auth: Any
    data: Any
    FILES: Any
    query_params: Any
    user: Any


class BaseSerializerProtocol(Protocol):
    """Typed proxy for ``rest_framework.serializers.BaseSerializer``."""

    data: object

    @property
    def validated_data(self) -> SerializerData | list[SerializerData]: ...

    def is_valid(self, *, raise_exception: bool = False) -> None: ...

    def save(self, **kwargs: object) -> object: ...


class SerializerProtocol(BaseSerializerProtocol, Protocol):
    """Typed proxy for ``rest_framework.serializers.Serializer``."""

    @property
    def validated_data(self) -> SerializerData: ...


class ListSerializerProtocol(BaseSerializerProtocol, Protocol):
    """Typed proxy for ``rest_framework.serializers.ListSerializer``."""

    @property
    def validated_data(self) -> list[SerializerData]: ...


class GenericAPIViewProtocol(Protocol):
    """Typed proxy for ``rest_framework.generics.GenericAPIView``."""

    def permission_denied(
        self,
        request: Request,
        message: str | None = None,
        code: str | None = None,
    ) -> None: ...

    def get_serializer(self, *args: Any, **kwargs: Any) -> SerializerProtocol: ...

    def get_queryset(self) -> QuerySetProtocol: ...

    def filter_queryset(self, queryset: QuerySetProtocol) -> QuerySetProtocol: ...


class QuerySetProtocol(Protocol):
    """Typed proxy for the Django ``QuerySet`` methods used by DRF helpers."""

    model: type[Any]

    def __iter__(self) -> Iterator[object]: ...

    def count(self) -> int: ...

    def filter(self, *args: object, **kwargs: object) -> QuerySetProtocol: ...

    def exclude(self, *args: object, **kwargs: object) -> QuerySetProtocol: ...


class ModelViewSetProtocol(GenericAPIViewProtocol, Protocol):
    """Typed proxy for ``rest_framework.viewsets.ModelViewSet``."""

    def get_success_headers(self, data: object) -> Mapping[str, str]: ...


class CreateModelMixinProtocol(Protocol):
    """Typed proxy for ``rest_framework.mixins.CreateModelMixin``."""

    def perform_create(self, serializer: SerializerProtocol) -> None: ...


class UpdateModelMixinProtocol(Protocol):
    """Typed proxy for ``rest_framework.mixins.UpdateModelMixin``."""

    def perform_update(self, serializer: SerializerProtocol) -> None: ...


class ChoiceFieldProtocol(Protocol):
    """Typed proxy for ``rest_framework.serializers.ChoiceField``."""

    def to_internal_value(self, data: object) -> object: ...


class PrimaryKeyRelatedFieldProtocol(Protocol):
    """Typed proxy for ``rest_framework.relations.PrimaryKeyRelatedField``."""

    def __init__(self, **kwargs: object) -> None: ...

    def to_representation(self, value: object) -> object: ...
