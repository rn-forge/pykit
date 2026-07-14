from __future__ import annotations

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rest_framework import serializers  # noqa: E402

from rn_forge.django.drf.serializers.fields import (  # noqa: E402
    EnumChoiceField,
    NestedReadPrimaryKeyRelatedField,
)
from rn_forge.django.models import Status  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402

pytestmark = pytest.mark.unit


class _PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "content_type"]


class TestEnumChoiceField:
    def test_to_representation_uses_enum_lookup_when_enum_type_is_provided(
        self,
    ) -> None:
        field = EnumChoiceField(enum_type=Status)
        assert field.to_representation(Status.Active) == {
            "code": "A",
            "name": "Active",
        }

    def test_to_representation_returns_code_name_mapping(self) -> None:
        field = EnumChoiceField(choices=Status.choices)
        assert field.to_representation(Status.Active) == {
            "code": "A",
            "name": "Active",
        }

    def test_to_representation_none_returns_none(self) -> None:
        field = EnumChoiceField(choices=Status.choices)
        assert field.to_representation(None) is None

    def test_to_internal_value_accepts_mapping(self) -> None:
        field = EnumChoiceField(enum_type=Status)
        assert field.to_internal_value({"code": "I", "name": "Inactive"}) == "I"

    def test_to_internal_value_accepts_scalar(self) -> None:
        field = EnumChoiceField(enum_type=Status)
        assert field.to_internal_value("E") == "E"


@pytest.mark.django_db
class TestNestedReadPrimaryKeyRelatedField:
    def test_defaults_to_primary_key_representation(self) -> None:
        permission = Permission.objects.create(
            name="Can read inventory",
            codename="inventory_read",
            content_type=ContentType.objects.get_for_model(Permission),
        )
        field = NestedReadPrimaryKeyRelatedField(queryset=Permission.objects.all())
        assert field.to_representation(permission) == permission.pk

    def test_nested_read_returns_full_serializer_data(self) -> None:
        permission = Permission.objects.create(
            name="Can update inventory",
            codename="inventory_update",
            content_type=ContentType.objects.get_for_model(Permission),
        )
        field = NestedReadPrimaryKeyRelatedField(
            queryset=Permission.objects.all(),
            serializer_class=_PermissionSerializer,
        )
        assert field.to_representation(permission) == {
            "id": permission.pk,
            "name": "Can update inventory",
            "codename": "inventory_update",
            "content_type": permission.content_type.pk,
        }

    def test_nested_read_can_limit_output_fields(self) -> None:
        permission = Permission.objects.create(
            name="Can delete inventory",
            codename="inventory_delete",
            content_type=ContentType.objects.get_for_model(Permission),
        )
        field = NestedReadPrimaryKeyRelatedField(
            queryset=Permission.objects.all(),
            serializer_class=_PermissionSerializer,
            read_fields=["id", "name"],
        )
        assert field.to_representation(permission) == {
            "id": permission.pk,
            "name": "Can delete inventory",
        }
