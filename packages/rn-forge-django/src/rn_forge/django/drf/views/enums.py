"""DRF views for enum choice discovery."""

from __future__ import annotations

from typing import Any, Protocol, cast

from django.apps import apps
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rn_forge.django.drf.views.base import BaseAPIView
from rn_forge.django.models import BaseEnum

__all__ = ["EnumChoicesAPIView"]


class _AppConfigLike(Protocol):
    models_module: object | None


class EnumChoicesAPIView(BaseAPIView):
    """Return `BaseEnum` choices for a given Django app and enum class."""

    serializer_class = serializers.Serializer

    @staticmethod
    def _parse_filter(value: str | None) -> list[str] | None:
        if value is None:
            return None
        parsed = [item.strip() for item in value.split(",") if item.strip()]
        return parsed or None

    @staticmethod
    def _resolve_enum_class(app_label: str, enum_name: str) -> type[BaseEnum]:
        app_config = cast(_AppConfigLike, cast(Any, apps).get_app_config(app_label))
        models_module = app_config.models_module
        enum_class = getattr(models_module, enum_name, None) if models_module else None

        if not isinstance(enum_class, type) or not issubclass(enum_class, BaseEnum):
            raise NotFound(f"{app_label}.{enum_name} is not a valid BaseEnum")

        return enum_class

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        app_label = cast(str | None, kwargs.get("app"))
        enum_name = cast(str | None, kwargs.get("enum"))
        if not app_label or not enum_name:
            raise ValidationError("Both 'app' and 'enum' URL params are required")

        enum_class = self._resolve_enum_class(app_label, enum_name)
        data = enum_class.get_choices(
            code_filter=self._parse_filter(self.get_request_param("codes")),
            name_filter=self._parse_filter(self.get_request_param("names")),
        )

        return Response(data)
