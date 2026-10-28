"""Models behind the default account resolver."""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import models

__all__ = ["AccountState", "ExternalAccount"]


class ExternalAccount(models.Model):
    """The link from an external ``(issuer, subject)`` to a user.

    A service account is a link to the user that stands for the client.
    """

    issuer: models.CharField[str, str] = models.CharField(max_length=255)
    subject: models.CharField[str, str] = models.CharField(max_length=255)
    user: models.ForeignKey[AbstractBaseUser, AbstractBaseUser] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_accounts",
    )
    provider: models.CharField[str, str] = models.CharField(max_length=255, blank=True)
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [  # noqa: RUF012  # framework class attribute
            models.UniqueConstraint(
                fields=["issuer", "subject"], name="rn_forge_auth_external_account"
            )
        ]


class AccountState(models.Model):
    """The session version of a user; an absent row means ``0``."""

    user: models.OneToOneField[AbstractBaseUser, AbstractBaseUser] = (
        models.OneToOneField(
            settings.AUTH_USER_MODEL,
            on_delete=models.CASCADE,
            primary_key=True,
            related_name="+",
        )
    )
    session_version: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField(default=0)
    )
