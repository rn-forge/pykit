"""Runtime-safe type aliases for Django admin classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

__all__ = [
    "PermissionAdminBase",
    "UserAdminBase",
]

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser, Permission

    # Both are used as admin base classes below, so they must stay TypeAlias —
    # a PEP 695 "type" statement alias cannot be subclassed.
    PermissionAdminBase: TypeAlias = admin.ModelAdmin[Permission]  # NOSONAR(S6794)
    UserAdminBase: TypeAlias = DjangoUserAdmin[AbstractUser]  # NOSONAR(S6794)
else:
    PermissionAdminBase = admin.ModelAdmin
    UserAdminBase = DjangoUserAdmin
