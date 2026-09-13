from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import models

from rn_forge.django.models import (
    BaseModel,
    ImmutableModelMixin,
    VersionedModelMixin,
)
from rn_forge.web import DomainConflict

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class _VersionedOrder(VersionedModelMixin, BaseModel):
    reference = models.CharField(max_length=20)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"


class _StrictVersionedOrder(VersionedModelMixin, BaseModel):
    validate_on_save = True
    reference = models.CharField(max_length=5)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"


class _Ledger(ImmutableModelMixin, BaseModel):
    amount = models.IntegerField()

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_VersionedOrder, _StrictVersionedOrder, _Ledger)


def _order(**kwargs) -> _VersionedOrder:
    return _VersionedOrder.objects.create(
        reference="A", created_by="t", updated_by="t", **kwargs
    )


class TestVersionedModelMixin:
    def test_insert_leaves_version_at_one(self) -> None:
        assert _order().version == 1

    def test_update_bumps_version(self) -> None:
        order = _order()
        order.reference = "B"
        order.save()
        order.refresh_from_db()
        assert order.version == 2

    def test_partial_update_still_persists_the_bump(self) -> None:
        order = _order()
        order.reference = "C"
        order.save(update_fields=["reference"])
        order.refresh_from_db()
        assert (order.reference, order.version) == ("C", 2)

    def test_in_memory_instance_is_not_stale(self) -> None:
        order = _order()
        order.save()
        assert order.version == 2

    def test_base_model_validation_still_runs(self) -> None:
        order = _StrictVersionedOrder(reference="ok", created_by="t", updated_by="t")
        order.save()
        order.reference = "far-too-long"
        with pytest.raises(ValidationError):
            order.save()


class TestImmutableModelMixin:
    def _ledger(self) -> _Ledger:
        return _Ledger.objects.create(amount=10, created_by="t", updated_by="t")

    def test_initial_insert_is_permitted(self) -> None:
        assert self._ledger().pk is not None

    def test_field_change_is_rejected(self) -> None:
        ledger = self._ledger()
        ledger.amount = 11
        with pytest.raises(DomainConflict):
            ledger.save()

    def test_audit_field_change_is_permitted(self) -> None:
        ledger = self._ledger()
        ledger.updated_by = "someone-else"
        ledger.save()
        ledger.refresh_from_db()
        assert ledger.updated_by == "someone-else"

    def test_delete_is_rejected(self) -> None:
        ledger = self._ledger()
        with pytest.raises(DomainConflict):
            ledger.delete()
        assert _Ledger.objects.filter(pk=ledger.pk).exists()
