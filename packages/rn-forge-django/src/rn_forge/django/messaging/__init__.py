"""Transactional outbox and inbox messaging over the Django ORM.

Import from the submodules; this app package cannot import models before
Django's app registry is ready.
"""

from rn_forge.django.messaging.apps import MessagingConfig

__all__ = ["MessagingConfig"]
