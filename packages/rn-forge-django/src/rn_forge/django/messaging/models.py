"""Abstract transactional outbox and inbox models."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import models
from django.utils import timezone

__all__ = ["AbstractInboxMessage", "AbstractOutboxMessage"]


class AbstractOutboxMessage(models.Model):
    """An event written in the same transaction as the change that caused it.

    Preserve the ``(published_at, occurred_at)`` index when overriding ``Meta``.
    """

    message_id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    message_type: models.CharField[str, str] = models.CharField(max_length=200)
    destination: models.CharField[str, str] = models.CharField(max_length=200)
    payload: models.JSONField[object, object] = models.JSONField(default=dict)
    occurred_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        default=timezone.now
    )
    published_at: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True, blank=True)
    )

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["published_at", "occurred_at"])]


class AbstractInboxMessage(models.Model):
    """A received message, recorded so a redelivery is recognised.

    ``message_id`` accepts identifiers assigned by either the sender or broker.
    """

    message_id: models.CharField[str, str] = models.CharField(
        max_length=200, unique=True
    )
    message_type: models.CharField[str, str] = models.CharField(max_length=200)
    received_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        default=timezone.now
    )
    processed_at: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True, blank=True)
    )
    attempts: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        default=0
    )
    error: models.TextField[str, str] = models.TextField(blank=True, default="")

    class Meta:
        abstract = True
