"""Reusable DRF serializer bases for rn-forge-django."""

from typing import ClassVar

from rest_framework import serializers
from rn_forge.django.drf.serializers.fields import EnumChoiceField
from rn_forge.django.models import Status

__all__ = ["BaseModelSerializer"]


class BaseModelSerializer(serializers.ModelSerializer):
    """Opinionated base serializer for models derived from ``BaseModel``."""

    status = EnumChoiceField(enum_type=Status, required=False)
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_by = serializers.CharField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    BASE_MODEL_FIELDS: ClassVar[list[str]] = [
        "status",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    ]
