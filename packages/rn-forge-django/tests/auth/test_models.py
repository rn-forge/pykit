"""Tests for standard Django auth behavior used by rn-forge auth."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

User = get_user_model()


class TestUserModel:
    def test_create_user_sets_username_and_password(self) -> None:
        user = User.objects.create_user(
            username="rohit",
            email="user@example.com",
            password="secret",
        )

        assert user.username == "rohit"
        assert user.email == "user@example.com"
        assert user.check_password("secret") is True

    def test_create_superuser_sets_required_flags(self) -> None:
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )

        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.is_active is True


class TestPermissionResolution:
    def _permission(self, codename: str, name: str | None = None) -> Permission:
        return Permission.objects.create(
            name=name or codename,
            codename=codename,
            content_type=ContentType.objects.get_for_model(User),
        )

    def _group(self, name: str) -> Group:
        return Group.objects.create(name=name)

    def _user(self, email: str = "user@example.com", username: str = "user") -> User:
        return User.objects.create_user(
            username=username,
            email=email,
            password="secret",
        )

    def test_has_direct_permission(self) -> None:
        user = self._user("direct@example.com", "direct")
        permission = self._permission("inventory_read")
        user.user_permissions.add(permission)

        assert (
            user.has_perm(f"{permission.content_type.app_label}.{permission.codename}")
            is True
        )
        assert (
            f"{permission.content_type.app_label}.{permission.codename}"
            in user.get_all_permissions()
        )

    def test_has_group_permission(self) -> None:
        user = self._user("group@example.com", "group")
        permission = self._permission("inventory_update")
        group = self._group("Editors")
        group.permissions.add(permission)
        user.groups.add(group)

        assert (
            user.has_perm(f"{permission.content_type.app_label}.{permission.codename}")
            is True
        )

    def test_superuser_short_circuits_permission_checks(self) -> None:
        user = User.objects.create_superuser(
            username="super",
            email="super@example.com",
            password="secret",
        )

        assert user.has_perm("anything.at.all") is True
        assert user.has_module_perms("inventory") is True


class TestStandardAuthNaming:
    def test_groups_are_used_for_roles(self) -> None:
        user = User.objects.create_user(
            username="roles",
            email="roles@example.com",
            password="secret",
        )
        group = Group.objects.create(name="Managers")
        user.groups.add(group)

        assert list(user.groups.values_list("name", flat=True)) == ["Managers"]
