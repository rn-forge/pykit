from __future__ import annotations

from collections.abc import Generator, Sequence

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from django.db import models  # noqa: E402
from django.db import connection  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.mixins import CreateModelMixin  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.viewsets import GenericViewSet  # noqa: E402

from rn_forge.django.drf._typing import SerializerData  # noqa: E402
from rn_forge.django.drf.views.bulk import (  # noqa: E402
    BulkCreateViewMixin,
    BulkDeleteViewMixin,
)
from rn_forge.django.drf.views.renderers import TransferColumn  # noqa: E402
from rn_forge.django.drf.views.transfer import (  # noqa: E402
    BulkLoadImportViewMixin,
    SnapshotImportViewMixin,
    UpsertImportViewMixin,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


class _BulkWidget(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, default="")

    class Meta:
        app_label = "tests"


class _ImportWidget(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        app_label = "tests"


class _CompoundImportWidget(models.Model):
    region = models.CharField(max_length=20)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)

    class Meta:
        app_label = "tests"
        unique_together = ("region", "code")


class _BulkWidgetSerializer(serializers.ModelSerializer[_BulkWidget]):
    class Meta:
        model = _BulkWidget
        fields = ["id", "name", "created_by"]


class _ImportWidgetSerializer(serializers.ModelSerializer[_ImportWidget]):
    class Meta:
        model = _ImportWidget
        fields = ["id", "code", "name"]


class _CompoundImportWidgetSerializer(
    serializers.ModelSerializer[_CompoundImportWidget]
):
    class Meta:
        model = _CompoundImportWidget
        fields = ["id", "region", "code", "name"]


class _BulkCreateView(BulkCreateViewMixin, CreateModelMixin, GenericViewSet):
    serializer_class = _BulkWidgetSerializer
    queryset = _BulkWidget.objects.all()

    def prepare_bulk_create_item(self, item: SerializerData) -> SerializerData:
        item["created_by"] = "tester@example.com"
        return item


class _GuardedBulkCreateView(_BulkCreateView):
    def validate_bulk_create_item(self, item: SerializerData) -> str | None:
        if item.get("name") == "blocked":
            return "blocked"
        return None


class _BulkDeleteView(BulkDeleteViewMixin, GenericViewSet):
    serializer_class = _BulkWidgetSerializer
    queryset = _BulkWidget.objects.all()


class _GuardedBulkDeleteView(_BulkDeleteView):
    def validate_bulk_delete_instance(self, instance: _BulkWidget) -> str | None:
        if instance.name == "blocked":
            return "blocked"
        return None


class _ImportWidgetView(UpsertImportViewMixin, GenericViewSet):
    serializer_class = _ImportWidgetSerializer
    queryset = _ImportWidget.objects.all()
    transfer_columns = TransferColumn.from_mapping({"Code": "code", "Name": "name"})

    def get_import_lookup_fields(self) -> tuple[str, ...]:
        return ("code",)

    def get_import_update_fields(self) -> tuple[str, ...]:
        return ("name",)


class _SmallBatchImportWidgetView(_ImportWidgetView):
    import_lookup_batch_size = 1


class _CompoundImportWidgetView(UpsertImportViewMixin, GenericViewSet):
    serializer_class = _CompoundImportWidgetSerializer
    queryset = _CompoundImportWidget.objects.all()
    transfer_columns = TransferColumn.from_mapping(
        {"Region": "region", "Code": "code", "Name": "name"}
    )

    def get_import_lookup_fields(self) -> tuple[str, ...]:
        return ("region", "code")

    def get_import_update_fields(self) -> tuple[str, ...]:
        return ("name",)


class _SnapshotImportWidgetView(SnapshotImportViewMixin, GenericViewSet):
    serializer_class = _ImportWidgetSerializer
    queryset = _ImportWidget.objects.all()
    transfer_columns = TransferColumn.from_mapping({"Code": "code", "Name": "name"})

    def get_import_lookup_fields(self) -> tuple[str, ...]:
        return ("code",)

    def get_import_update_fields(self) -> tuple[str, ...]:
        return ("name",)


class _SoftDeleteSnapshotImportWidgetView(_SnapshotImportWidgetView):
    def delete_missing_import_instances(
        self,
        request: object,
        instances: Sequence[object],
    ) -> int:
        del request
        deleted = 0
        for instance in instances:
            widget = instance
            assert isinstance(widget, _ImportWidget)
            widget.name = "soft-deleted"
            widget.save(update_fields=["name"])
            deleted += 1
        return deleted


class _BulkLoadImportWidgetView(BulkLoadImportViewMixin, GenericViewSet):
    serializer_class = _ImportWidgetSerializer
    queryset = _ImportWidget.objects.all()


@pytest.fixture(autouse=True)
def _bulk_widget_schema() -> Generator[None, None, None]:
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(_BulkWidget)
        schema_editor.create_model(_ImportWidget)
        schema_editor.create_model(_CompoundImportWidget)
    try:
        yield
    finally:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(_CompoundImportWidget)
            schema_editor.delete_model(_ImportWidget)
            schema_editor.delete_model(_BulkWidget)


class TestBulkCreateViewMixin:
    def teardown_method(self) -> None:
        _BulkWidget.objects.all().delete()

    def test_bulk_create_creates_records(self) -> None:
        view = _BulkCreateView.as_view({"post": "bulk_create"})
        request = APIRequestFactory().post(
            "/widgets/bulk-create/",
            [{"name": "alpha"}, {"name": "beta"}],
            format="json",
        )

        response = view(request)

        assert response.status_code == 201
        assert _BulkWidget.objects.count() == 2
        assert list(_BulkWidget.objects.values_list("created_by", flat=True)) == [
            "tester@example.com",
            "tester@example.com",
        ]

    def test_bulk_create_requires_list_payload(self) -> None:
        view = _BulkCreateView.as_view({"post": "bulk_create"})
        request = APIRequestFactory().post(
            "/widgets/bulk-create/",
            {"name": "alpha"},
            format="json",
        )

        response = view(request)

        assert response.status_code == 400
        assert response.data == {"message": "Request data must be a list of objects"}

    def test_bulk_create_denies_on_validation_hook(self) -> None:
        view = _GuardedBulkCreateView.as_view({"post": "bulk_create"})
        request = APIRequestFactory().post(
            "/widgets/bulk-create/",
            [{"name": "blocked"}],
            format="json",
        )

        response = view(request)

        assert response.status_code == 403
        assert _BulkWidget.objects.count() == 0


class TestBulkDeleteViewMixin:
    def teardown_method(self) -> None:
        _BulkWidget.objects.all().delete()

    def test_bulk_delete_removes_records(self) -> None:
        first = _BulkWidget.objects.create(name="alpha")
        second = _BulkWidget.objects.create(name="beta")
        view = _BulkDeleteView.as_view({"delete": "bulk_delete"})
        request = APIRequestFactory().delete(
            "/widgets/bulk-delete/",
            {"ids": [first.pk, second.pk]},
            format="json",
        )

        response = view(request)

        assert response.status_code == 204
        assert _BulkWidget.objects.count() == 0

    def test_bulk_delete_requires_ids(self) -> None:
        view = _BulkDeleteView.as_view({"delete": "bulk_delete"})
        request = APIRequestFactory().delete(
            "/widgets/bulk-delete/",
            {"ids": []},
            format="json",
        )

        response = view(request)

        assert response.status_code == 400
        assert response.data == {"message": "No IDs provided"}

    def test_bulk_delete_denies_on_validation_hook(self) -> None:
        blocked = _BulkWidget.objects.create(name="blocked")
        view = _GuardedBulkDeleteView.as_view({"delete": "bulk_delete"})
        request = APIRequestFactory().delete(
            "/widgets/bulk-delete/",
            {"ids": [blocked.pk]},
            format="json",
        )

        response = view(request)

        assert response.status_code == 403
        assert _BulkWidget.objects.count() == 1


class TestUpsertImportViewMixin:
    def teardown_method(self) -> None:
        _ImportWidget.objects.all().delete()
        _CompoundImportWidget.objects.all().delete()

    def test_upload_upserts_records(self) -> None:
        existing = _ImportWidget.objects.create(code="A", name="Alpha")
        view = _ImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [
                {"Code": "A", "Name": "Alpha Updated"},
                {"Code": "B", "Name": "Beta"},
            ],
            format="json",
        )

        response = view(request)

        existing.refresh_from_db()
        assert response.status_code == 201
        assert response.data == {"created": 1, "updated": 1, "errors": []}
        assert existing.name == "Alpha Updated"
        assert _ImportWidget.objects.get(code="B").name == "Beta"

    def test_upload_supports_multi_field_natural_key(self) -> None:
        existing = _CompoundImportWidget.objects.create(
            region="north",
            code="A",
            name="Alpha",
        )
        _CompoundImportWidget.objects.create(region="south", code="A", name="Other")
        view = _CompoundImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [{"Region": "north", "Code": "A", "Name": "Alpha Updated"}],
            format="json",
        )

        response = view(request)

        existing.refresh_from_db()
        assert response.status_code == 201
        assert response.data == {"created": 0, "updated": 1, "errors": []}
        assert existing.name == "Alpha Updated"
        assert (
            _CompoundImportWidget.objects.get(region="south", code="A").name == "Other"
        )

    def test_lookup_batch_size_is_capped_and_still_upserts(self) -> None:
        _ImportWidget.objects.create(code="A", name="Alpha")
        _ImportWidget.objects.create(code="B", name="Beta")
        view = _SmallBatchImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [
                {"Code": "A", "Name": "Alpha Updated"},
                {"Code": "B", "Name": "Beta Updated"},
            ],
            format="json",
        )

        response = view(request)

        assert response.status_code == 201
        assert response.data == {"created": 0, "updated": 2, "errors": []}
        assert _ImportWidget.objects.get(code="A").name == "Alpha Updated"
        assert _ImportWidget.objects.get(code="B").name == "Beta Updated"

    def test_row_errors_prevent_persistence(self) -> None:
        view = _ImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [{"Code": "A"}],
            format="json",
        )

        response = view(request)

        assert response.status_code == 400
        assert _ImportWidget.objects.count() == 0


class TestSnapshotImportViewMixin:
    def teardown_method(self) -> None:
        _ImportWidget.objects.all().delete()

    def test_snapshot_does_not_delete_missing_without_flag(self) -> None:
        _ImportWidget.objects.create(code="A", name="Alpha")
        _ImportWidget.objects.create(code="C", name="Gamma")
        view = _SnapshotImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [
                {"Code": "A", "Name": "Alpha Updated"},
                {"Code": "B", "Name": "Beta"},
            ],
            format="json",
        )

        response = view(request)

        assert response.status_code == 201
        assert response.data == {"created": 1, "updated": 1, "errors": []}
        assert _ImportWidget.objects.filter(code="C").exists()

    def test_snapshot_deletes_missing_with_flag(self) -> None:
        _ImportWidget.objects.create(code="A", name="Alpha")
        _ImportWidget.objects.create(code="C", name="Gamma")
        view = _SnapshotImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json&delete-missing=true",
            [{"Code": "A", "Name": "Alpha Updated"}],
            format="json",
        )

        response = view(request)

        assert response.status_code == 201
        assert response.data == {"created": 0, "updated": 1, "errors": [], "deleted": 1}
        assert not _ImportWidget.objects.filter(code="C").exists()

    def test_snapshot_delete_hook_can_soft_delete(self) -> None:
        _ImportWidget.objects.create(code="A", name="Alpha")
        missing = _ImportWidget.objects.create(code="C", name="Gamma")
        view = _SoftDeleteSnapshotImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json&delete-missing=true",
            [{"Code": "A", "Name": "Alpha Updated"}],
            format="json",
        )

        response = view(request)

        missing.refresh_from_db()
        assert response.status_code == 201
        assert response.data == {"created": 0, "updated": 1, "errors": [], "deleted": 1}
        assert missing.name == "soft-deleted"


class TestBulkLoadImportViewMixin:
    def teardown_method(self) -> None:
        _ImportWidget.objects.all().delete()

    def test_bulk_load_creates_and_updates_db_shaped_rows(self) -> None:
        existing = _ImportWidget.objects.create(code="A", name="Alpha")
        view = _BulkLoadImportWidgetView.as_view({"post": "import_items"})
        request = APIRequestFactory().post(
            "/widgets/import/?format=json",
            [
                {"id": existing.pk, "code": "A", "name": "Alpha Updated"},
                {"code": "B", "name": "Beta"},
            ],
            format="json",
        )

        response = view(request)

        existing.refresh_from_db()
        assert response.status_code == 201
        assert response.data == {"created": 1, "updated": 1, "errors": []}
        assert existing.name == "Alpha Updated"
        assert _ImportWidget.objects.get(code="B").name == "Beta"
