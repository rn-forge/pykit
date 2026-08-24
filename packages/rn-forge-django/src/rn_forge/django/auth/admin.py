"""Admin registrations for standard Django auth models."""

from typing import Any, cast

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.auth import get_user_model

from rn_forge.django.auth._typing import PermissionAdminBase, UserAdminBase

register_model = cast(Any, admin.register)

User: type[AbstractUser] = cast(type[AbstractUser], get_user_model())


@register_model(Permission)
class PermissionAdmin(PermissionAdminBase):
    list_display = ("name", "content_type", "codename")
    list_filter = ("content_type",)
    search_fields = ("name", "codename")
    ordering = ("content_type", "codename")


@register_model(Group)
class GroupAdmin(DjangoGroupAdmin):
    pass


@register_model(User)
class UserAdmin(UserAdminBase):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = (
        "last_login",
        "date_joined",
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
