import pytest
from django.db import models

from rn_forge.django.drf.serializers.base import BaseModelSerializer
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
