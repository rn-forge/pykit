"""Django app configuration for ``rn_forge.django.messaging``."""

from django.apps import AppConfig

__all__ = ["MessagingConfig"]


class MessagingConfig(AppConfig):
    """The messaging app. Its models are abstract, so it adds no tables."""

    name = "rn_forge.django.messaging"
    label = "rn_forge_django_messaging"
    verbose_name = "rn-forge messaging"
