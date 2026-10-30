"""Auth-aware DRF view mixins and base views."""

from __future__ import annotations

from typing import cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission
from rn_forge.django.auth.drf.authorization import PermissionKeyPermission
from rn_forge.django.auth.drf.serializers import (
    GroupSerializer,
    PermissionSerializer,
    UserSerializer,
)
from rn_forge.django.drf.views.base import BaseAPIView, BaseModelViewSet

__all__ = [
    "AuthorizedAPIView",
    "AuthorizedModelViewSet",
    "GroupViewSet",
    "PermissionViewSet",
    "UserViewSet",
]

User: type[AbstractUser] = cast(type[AbstractUser], get_user_model())


class AuthorizedAPIView(BaseAPIView):
    """API view that requires the permission its ``permission_key`` and action map to.

    Checked by :class:`~rn_forge.django.auth.drf.authorization.PermissionKeyPermission`.
    """

    permission_classes = [PermissionKeyPermission]  # noqa: RUF012  # framework class attribute


class AuthorizedModelViewSet(BaseModelViewSet):
    """Model viewset that requires the permission its ``permission_key`` and action map to.

    Checked by :class:`~rn_forge.django.auth.drf.authorization.PermissionKeyPermission`.
    """

    permission_classes = [PermissionKeyPermission]  # noqa: RUF012  # framework class attribute


class PermissionViewSet(AuthorizedModelViewSet):
    """Auth permission management viewset."""

    queryset = Permission.objects.select_related("content_type")
    serializer_class = PermissionSerializer
    permission_key = "rn_forge.auth.permission"


class GroupViewSet(AuthorizedModelViewSet):
    """Auth group management viewset."""

    queryset = Group.objects.prefetch_related("permissions")
    serializer_class = GroupSerializer
    permission_key = "rn_forge.auth.group"


class UserViewSet(AuthorizedModelViewSet):
    """Auth user management viewset."""

    queryset = User.objects.prefetch_related("groups", "user_permissions")
    serializer_class = UserSerializer
    permission_key = "rn_forge.auth.user"
