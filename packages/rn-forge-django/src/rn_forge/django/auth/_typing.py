"""Internal typing helpers for the auth package's admin integration.

``ModelAdmin`` generics exist only in django-stubs and the runtime classes are
not subscriptable, so the base classes are aliased under ``TYPE_CHECKING`` with
plain runtime fallbacks — the same approach as :mod:`rn_forge.django._typing`.

These aliases are kept out of the top-level ``_typing`` module on purpose:
importing ``django.contrib.admin`` touches the app registry, which fails when
pulled in transitively from ``models.base`` before ``django.setup()`` runs.
"""

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
    PermissionAdminBase: TypeAlias = admin.ModelAdmin[Permission]
    UserAdminBase: TypeAlias = DjangoUserAdmin[AbstractUser]
else:
    PermissionAdminBase = admin.ModelAdmin
    UserAdminBase = DjangoUserAdmin
