from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from rn_forge.django.auth.drf.serializers import UserSerializer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

User = get_user_model()


class TestUserSerializer:
    def test_create_uses_create_user_and_assigns_m2m_relations(self) -> None:
        group = Group.objects.create(name="Managers")
        permission = Permission.objects.create(
            name="Can review inventory",
            codename="review_inventory",
            content_type=ContentType.objects.get_for_model(User),
        )
        serializer = UserSerializer(
            data={
                "username": "serializer-user",
                "email": "serializer@example.com",
                "first_name": "Serial",
                "last_name": "Izer",
                "password": "secret",
                "groups": [group.pk],
                "user_permissions": [permission.pk],
            }
        )

        assert serializer.is_valid(), serializer.errors

        user = serializer.save()

        assert user.email == "serializer@example.com"
        assert user.check_password("secret") is True
        assert list(user.groups.values_list("name", flat=True)) == ["Managers"]
        assert list(user.user_permissions.values_list("codename", flat=True)) == [
            "review_inventory"
        ]

    def test_update_delegates_m2m_assignment_and_sets_password(self) -> None:
        original_group = Group.objects.create(name="Managers")
        updated_group = Group.objects.create(name="Editors")
        original_permission = Permission.objects.create(
            name="Can review inventory",
            codename="review_inventory",
            content_type=ContentType.objects.get_for_model(User),
        )
        updated_permission = Permission.objects.create(
            name="Can approve inventory",
            codename="approve_inventory",
            content_type=ContentType.objects.get_for_model(User),
        )
        user = User.objects.create_user(
            username="serializer-user",
            email="serializer@example.com",
            password="secret",
        )
        user.groups.add(original_group)
        user.user_permissions.add(original_permission)

        serializer = UserSerializer(
            user,
            data={
                "first_name": "Updated",
                "groups": [updated_group.pk],
                "user_permissions": [updated_permission.pk],
                "password": "new-secret",
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

        updated_user = serializer.save()

        assert updated_user.first_name == "Updated"
        assert updated_user.check_password("new-secret") is True
        assert list(updated_user.groups.values_list("name", flat=True)) == ["Editors"]
        assert list(
            updated_user.user_permissions.values_list("codename", flat=True)
        ) == ["approve_inventory"]
