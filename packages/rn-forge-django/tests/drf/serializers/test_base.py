import pytest
from django.db import models
from rest_framework import serializers

from rn_forge.django.drf.serializers.base import BaseModelSerializer, OmitEmptyMixin
from rn_forge.django.drf.serializers.fields import EnumChoiceField
from rn_forge.django.models import (
    BaseModel,
    DateRangeModel,
    NaturalKeyLookupManager,
    Status,
)


pytestmark = pytest.mark.unit


class _Widget(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    objects = NaturalKeyLookupManager()

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"

    @classmethod
    def natural_keys(cls) -> list[str]:
        return ["code"]


class _WidgetSerializer(BaseModelSerializer):
    class Meta:
        model = _Widget
        fields = [
            "name",
            "code",
            *BaseModelSerializer.BASE_MODEL_FIELDS,
        ]


def test_base_model_serializer_date_range_constant() -> None:
    assert DateRangeModel.DATE_RANGE_ACTIVE_FIELD == "is_date_range_active"


def test_base_model_serializer_base_model_fields() -> None:
    assert BaseModelSerializer.BASE_MODEL_FIELDS == [
        "status",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    ]


def test_base_model_serializer_declares_status_field() -> None:
    serializer = _WidgetSerializer()
    field = serializer.fields["status"]

    assert isinstance(field, EnumChoiceField)
    assert field.enum_type is Status
    assert field.required is False


def test_base_model_serializer_marks_audit_fields_read_only() -> None:
    serializer = _WidgetSerializer()

    for field_name in ["created_by", "created_at", "updated_by", "updated_at"]:
        assert serializer.fields[field_name].read_only is True
    assert serializer.fields["status"].read_only is False


class _OmitEmpty(OmitEmptyMixin):
    required_name = serializers.CharField(allow_null=True, allow_blank=True)
    note = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    count = serializers.IntegerField(required=False)
    flag = serializers.BooleanField(required=False)
    tags = serializers.ListField(required=False)


class _OmitEmptyWidgetSerializer(OmitEmptyMixin, BaseModelSerializer):
    class Meta:
        model = _Widget
        fields = ["name", "code", *BaseModelSerializer.BASE_MODEL_FIELDS]


def _omit(**values):
    base = {"required_name": "x", "note": "n", "count": 1, "flag": True, "tags": ["t"]}
    return _OmitEmpty({**base, **values}).data


def test_omit_empty_strips_optional_none_and_blank() -> None:
    assert "note" not in _omit(note=None)
    assert "note" not in _omit(note="")


def test_omit_empty_keeps_required_empty_fields() -> None:
    data = _omit(required_name=None)
    assert data["required_name"] is None


def test_omit_empty_keeps_zero_false_and_empty_list() -> None:
    data = _omit(count=0, flag=False, tags=[])
    assert (data["count"], data["flag"], data["tags"]) == (0, False, [])


def test_omit_empty_composes_with_base_model_serializer() -> None:
    serializer = _OmitEmptyWidgetSerializer()
    for field_name in ["created_by", "created_at", "updated_by", "updated_at"]:
        assert serializer.fields[field_name].read_only is True
    widget = _Widget(name="n", code="", created_by="u", updated_by="u")
    data = _OmitEmptyWidgetSerializer(widget).data
    assert data["name"] == "n"
    assert data["code"] == ""
    assert "created_at" not in data
