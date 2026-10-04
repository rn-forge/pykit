"""Soft-delete model mixin and queryset (AIP-164)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from django.db import models
from django.utils import timezone
from rn_forge.django._typing import StrField
from rn_forge.django.models.base import NaturalKeyLookupManager

__all__ = ["SoftDeleteModelMixin", "SoftDeleteQuerySet"]


class SoftDeleteQuerySet(models.QuerySet[Any]):
    """A queryset that can select live or soft-deleted rows."""

    def live(self) -> Self:
        """Return the rows whose ``delete_time`` is ``None``."""
        return self.filter(delete_time__isnull=True)

    def deleted(self) -> Self:
        """Return the rows whose ``delete_time`` is set."""
        return self.filter(delete_time__isnull=False)


SoftDeleteManager = NaturalKeyLookupManager.from_queryset(SoftDeleteQuerySet)


class SoftDeleteModelMixin(models.Model):
    """Abstract mixin adding a nullable, indexed ``delete_time`` column.

    List it before :class:`~rn_forge.django.models.BaseModel`. The default
    manager is **not** filtered; select with ``.live()`` or ``.deleted()``.
    Saving a :class:`~rn_forge.django.models.VersionedModelMixin` model through
    :meth:`soft_delete` or :meth:`undelete` bumps its version as any save does.
    """

    delete_time: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True, blank=True, db_index=True)
    )
    updated_by: StrField

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def get_delete_time(self) -> datetime:
        """Return the time :meth:`soft_delete` records; the current UTC time."""
        return timezone.now()

    def soft_delete(self, *, actor: str) -> None:
        """Set ``delete_time``, record *actor* in ``updated_by`` and save."""
        self.delete_time = self.get_delete_time()
        self.updated_by = actor
        self.save()

    def undelete(self, *, actor: str) -> None:
        """Clear ``delete_time``, record *actor* in ``updated_by`` and save."""
        self.delete_time = None
        self.updated_by = actor
        self.save()
