from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.db import models

from rn_forge.django.models import (
    BaseModel,
    SoftDeleteModelMixin,
    SoftDeleteQuerySet,
    VersionedModelMixin,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PINNED = datetime(2026, 1, 2, tzinfo=UTC if settings.USE_TZ else None)


class _Note(SoftDeleteModelMixin, VersionedModelMixin, BaseModel):
    text = models.CharField(max_length=20)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"

    def get_delete_time(self) -> datetime:
        return PINNED


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_Note)


def _note(text: str = "a") -> _Note:
    return _Note.objects.create(text=text, created_by="t", updated_by="t")


def test_a_new_row_is_live():
    assert _note().delete_time is None


def test_soft_delete_sets_the_time_the_actor_and_bumps_the_version():
    note = _note()

    note.soft_delete(actor="alice")

    stored = _Note.objects.get(pk=note.pk)
    assert stored.delete_time == PINNED
    assert stored.updated_by == "alice"
    assert stored.version == 2


def test_undelete_clears_the_time_and_bumps_the_version():
    note = _note()
    note.soft_delete(actor="alice")

    note.undelete(actor="bob")

    stored = _Note.objects.get(pk=note.pk)
    assert stored.delete_time is None
    assert stored.updated_by == "bob"
    assert stored.version == 3


def test_live_and_deleted_partition_the_rows():
    live, gone = _note("live"), _note("gone")
    gone.soft_delete(actor="alice")

    assert list(_Note.objects.live().filter(pk__in=[live.pk, gone.pk])) == [live]
    assert list(_Note.objects.deleted().filter(pk__in=[live.pk, gone.pk])) == [gone]


def test_the_default_manager_is_not_filtered():
    gone = _note()
    gone.soft_delete(actor="alice")

    assert _Note.objects.filter(pk=gone.pk).exists()
    assert isinstance(_Note.objects.all(), SoftDeleteQuerySet)
