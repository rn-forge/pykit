"""Django app configuration for the opinionated rn-forge auth app."""

from typing import ClassVar

from django.apps import AppConfig


class AuthConfig(AppConfig):
    """Register the auth app under a stable label for fixtures/admin/tests."""

    default_auto_field: ClassVar[str] = "django.db.models.BigAutoField"  # pyright: ignore[reportIncompatibleVariableOverride]
    name = "rn_forge.django.auth"
    label = "rn_forge_django_auth"
    verbose_name = "rn-forge-django Auth"
