"""Reusable DRF serializer fields for rn-forge-django."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast, override

from rest_framework import serializers
from rn_forge.django.drf._typing import (
    ChoiceFieldProtocol,
    PrimaryKeyRelatedFieldProtocol,
)
from rn_forge.django.drf.casing import RawDict, RawList
from rn_forge.django.models import BaseEnum

__all__ = [
    "EnumChoiceField",
    "NestedReadPrimaryKeyRelatedField",
    "RawPassthroughField",
]


# ---------------------------------------------------------------------------
# Serializer Fields
# ---------------------------------------------------------------------------


class EnumChoiceField(serializers.ChoiceField):
    """Choice field that renders values as ``{code, name}`` mappings."""

    def __init__(
        self,
        *args: Any,
        enum_type: type[BaseEnum] | None = None,
        **kwargs: Any,
    ) -> None:
        self.enum_type = enum_type
        if enum_type is not None:
            kwargs.setdefault("choices", enum_type)
        base_field = cast(ChoiceFieldProtocol, super())
        cast(Any, base_field).__init__(*args, **kwargs)

    @property
    def _typed_choices(self) -> Mapping[str, object]:
        """Return ``self.choices`` as a typed mapping for static analysis."""
        return cast(Mapping[str, object], self.choices)

    @override
    def to_representation(self, value: object) -> Mapping[str, object] | None:
        if value in ("", None):
            return None

        code = str(value)
        if self.enum_type is not None:
            return cast(Mapping[str, object], self.enum_type.lookup(code))

        label: object = self._typed_choices.get(code, value)
        return {"code": code, "name": str(label)}

    @override
    def to_internal_value(self, data: object) -> str:
        base_field = cast(ChoiceFieldProtocol, super())
        if isinstance(data, Mapping):
            payload = cast(Mapping[str, object], data)
            return str(base_field.to_internal_value(payload.get("code")))

        return str(base_field.to_internal_value(data))


class NestedReadPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Primary-key write field with optional nested read representation."""

    def __init__(
        self,
        *,
        serializer_class: type[serializers.Serializer] | None = None,
        read_fields: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.serializer_class = serializer_class
        self.read_fields = tuple(read_fields or ())
        base_field = cast(PrimaryKeyRelatedFieldProtocol, super())
        base_field.__init__(**kwargs)

    @override
    def to_representation(self, value: Any) -> Any:
        base_field = cast(PrimaryKeyRelatedFieldProtocol, super())
        if self.serializer_class is None:
            return base_field.to_representation(value)

        serializer = self.serializer_class(value, context=getattr(self, "context", {}))
        data = cast(Mapping[str, Any], serializer.data)
        if not self.read_fields:
            return dict(data)
        return {field: data[field] for field in self.read_fields if field in data}

    @override
    def use_pk_only_optimization(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Disable DRF's PK-only shortcut when nested read serialization is enabled."""
        return self.serializer_class is None


class RawPassthroughField(serializers.JSONField):
    """A JSON value whose keys stay verbatim under camelCase rendering and parsing.

    The parser matches field names at any depth, so another field with the same
    name in the request body is also passed through.
    """

    raw_passthrough: ClassVar[bool] = True

    @override
    def to_representation(self, value: Any) -> Any:
        representation = cast(object, super().to_representation(value))  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave JSONField untyped
        if isinstance(representation, Mapping):
            return RawDict(cast(Mapping[str, Any], representation))
        if isinstance(representation, list):
            return RawList(cast(list[Any], representation))
        return representation
