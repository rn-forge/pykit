"""Reusable DRF serializer bases for rn-forge-django."""

from collections.abc import Mapping
from typing import Any, ClassVar, cast, override

from rest_framework import serializers
from rn_forge.django.drf.serializers.fields import EnumChoiceField
from rn_forge.django.models import Status

__all__ = ["BaseModelSerializer", "OmitEmptyMixin"]

_EMPTY: tuple[object, ...] = (None, "")


class OmitEmptyMixin(serializers.Serializer):
    """Drop *optional* fields whose value is empty from ``to_representation``.

    **Empty means ``None`` or ``""`` only** — not ``0``, not ``False``, not
    ``[]``, not ``{}``. Those are values.

    **Only fields with ``required=False`` are stripped.** A required field is
    part of the contract the schema advertises, so it is emitted even when
    empty — including one declared ``allow_null=True``. The gate is DRF's own
    ``required`` flag rather than a separate list so the representation and the
    schema cannot disagree about which fields may be absent. Note that DRF sets
    ``required=False`` on every ``read_only`` field.
    """

    @override
    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = cast(Mapping[str, Any], super().to_representation(instance))  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave the parameter untyped
        optional = {
            name
            for name, field in cast(
                Mapping[str, serializers.Field], self.fields
            ).items()
            if not cast(bool, field.required)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave required partially untyped
        }
        return {
            name: value
            for name, value in data.items()
            if not (name in optional and any(value == empty for empty in _EMPTY))
        }


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
