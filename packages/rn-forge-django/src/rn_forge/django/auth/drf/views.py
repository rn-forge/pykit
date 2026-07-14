"""Auth-aware DRF view mixins and base views."""

from __future__ import annotations

from typing import cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission

from rn_forge.django.auth.drf.mixins import (
    AuthorizationViewMixin,
    PermissionKeyViewMixin,
)
from rn_forge.django.auth.drf.serializers import (
    GroupSerializer,
    PermissionSerializer,
    UserSerializer,
)
from rn_forge.django.drf.views import TransferColumn
from rn_forge.django.drf.views.base import (
    BaseAPIView,
    BaseModelViewSet,
    BulkLoadImportModelViewSet,
    ExportModelViewSet,
    SnapshotImportModelViewSet,
    UpsertImportModelViewSet,
)

__all__ = [
    "AuthorizedAPIView",
    "AuthorizedBulkLoadImportModelViewSet",
    "AuthorizedExportModelViewSet",
    "AuthorizedModelViewSet",
    "AuthorizedSnapshotImportModelViewSet",
    "AuthorizedUpsertImportModelViewSet",
    "GroupViewSet",
    "PermissionViewSet",
    "UserUpsertImportViewSet",
    "UserViewSet",
]

User: type[AbstractUser] = cast(type[AbstractUser], get_user_model())


class AuthorizedAPIView(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    BaseAPIView,
):
    """Opinionated DRF base view with auth permission defaults."""


class AuthorizedModelViewSet(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    BaseModelViewSet,
):
    """Auth-aware model viewset with bulk actions."""


class AuthorizedExportModelViewSet(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    ExportModelViewSet,
):
    """Auth-aware model viewset with bulk and export actions."""


class AuthorizedUpsertImportModelViewSet(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    UpsertImportModelViewSet,
):
    """Auth-aware model viewset with upsert import and export actions."""


class AuthorizedSnapshotImportModelViewSet(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    SnapshotImportModelViewSet,
):
    """Auth-aware model viewset with snapshot import and export actions."""


class AuthorizedBulkLoadImportModelViewSet(
    PermissionKeyViewMixin,
    AuthorizationViewMixin,
    BulkLoadImportModelViewSet,
):
    """Auth-aware model viewset with DB-shaped import and export actions."""


class PermissionViewSet(AuthorizedExportModelViewSet):
    """Auth permission management viewset."""

    queryset = Permission.objects.select_related("content_type")
    serializer_class = PermissionSerializer
    permission_key = "rn_forge.auth.permission"
    transfer_columns = TransferColumn.from_mapping(
        {
            "Name": "name",
            "Codename": "codename",
            "Content Type": "content_type.id",
        }
    )


class GroupViewSet(AuthorizedExportModelViewSet):
    """Auth group management viewset."""

    queryset = Group.objects.prefetch_related("permissions")
    serializer_class = GroupSerializer
    permission_key = "rn_forge.auth.group"
    transfer_columns = TransferColumn.from_mapping(
        {
            "Name": "name",
            "Permissions": "permissions",
        }
    )


class UserViewSet(AuthorizedExportModelViewSet):
    """Auth user management viewset."""

    queryset = User.objects.prefetch_related("groups", "user_permissions")
    serializer_class = UserSerializer
    permission_key = "rn_forge.auth.user"
    transfer_columns = TransferColumn.from_mapping(
        {
            "Username": "username",
            "First Name": "first_name",
            "Last Name": "last_name",
            "Email": "email",
            "Active": "is_active",
            "Staff": "is_staff",
            "Superuser": "is_superuser",
            "Groups": "groups",
            "User Permissions": "user_permissions",
            "Last Login": "last_login",
            "Date Joined": "date_joined",
        }
    )


class UserUpsertImportViewSet(AuthorizedUpsertImportModelViewSet):
    """User upsert import/export viewset for transfer API evaluation."""

    queryset = User.objects.prefetch_related("groups", "user_permissions")
    serializer_class = UserSerializer
    permission_key = "rn_forge.auth.user"
    transfer_columns = UserViewSet.transfer_columns
    import_columns = UserViewSet.transfer_columns

    def get_import_lookup_fields(self) -> tuple[str, ...]:
        return ("email",)

    def get_import_update_fields(self) -> tuple[str, ...]:
        return (
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )
