"""DRF serializers for standard Django auth models."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from rn_forge.django.drf.serializers import NestedReadPrimaryKeyRelatedField

__all__ = [
    "GroupSerializer",
    "PermissionSerializer",
    "UserSerializer",
]

User: type[AbstractUser] = cast(type[AbstractUser], get_user_model())
USER_MANY_TO_MANY_FIELDS = ("groups", "user_permissions")


class ContentTypeSerializer(serializers.ModelSerializer):
    """Serializer for content types referenced by permissions."""

    class Meta:
        model = ContentType
        fields = [
            "id",
            "app_label",
            "model",
        ]
        read_only_fields = ["id"]


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Django permissions."""

    content_type = NestedReadPrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        serializer_class=ContentTypeSerializer,
        read_fields=["id", "app_label", "model"],
    )

    class Meta:
        model = Permission
        fields = [
            "id",
            "name",
            "content_type",
            "codename",
        ]
        read_only_fields = ["id"]


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Django groups."""

    permissions = NestedReadPrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        serializer_class=PermissionSerializer,
        read_fields=["id", "name", "codename"],
        many=True,
        required=False,
    )

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "permissions",
        ]
        read_only_fields = ["id"]


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the active Django user model."""

    groups = NestedReadPrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        serializer_class=GroupSerializer,
        read_fields=["id", "name"],
        many=True,
        required=False,
    )
    user_permissions = NestedReadPrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        serializer_class=PermissionSerializer,
        read_fields=["id", "name", "codename"],
        many=True,
        required=False,
    )
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
            "password",
            "last_login",
            "date_joined",
        ]
        read_only_fields = ["id", "last_login", "date_joined"]

    @staticmethod
    def _pop_many_to_many(validated_data: dict[str, Any]) -> dict[str, object]:
        many_to_many: dict[str, object] = {}
        for field_name in USER_MANY_TO_MANY_FIELDS:
            if field_name in validated_data:
                many_to_many[field_name] = validated_data.pop(field_name)
        return many_to_many

    def create(self, validated_data: dict[str, Any]) -> AbstractUser:
        many_to_many = self._pop_many_to_many(validated_data)
        manager = getattr(User, "_default_manager")
        user: Any = manager.create_user(**validated_data)
        for field_name, value in many_to_many.items():
            getattr(user, field_name).set(value)
        return cast(AbstractUser, user)

    def update(
        self, instance: AbstractUser, validated_data: dict[str, Any]
    ) -> AbstractUser:
        password = validated_data.pop("password", None)
        update_user = getattr(super(), "update")
        user: Any = update_user(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return cast(AbstractUser, user)
