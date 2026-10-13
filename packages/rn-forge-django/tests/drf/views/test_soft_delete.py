from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.db import models
from django.test import Client, override_settings
from rest_framework import serializers

pytest.importorskip("drf_spectacular")

from drf_spectacular.generators import SchemaGenerator  # noqa: E402
from drf_spectacular.settings import patched_settings  # noqa: E402

from rn_forge.django.drf.casing import CamelCaseJSONRenderer  # noqa: E402
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS  # noqa: E402
from rn_forge.django.drf.routers import CustomMethodRouter  # noqa: E402
from rn_forge.django.drf.transfer import BatchDeleteMixin  # noqa: E402
from rn_forge.django.drf.views.base import BaseModelViewSet  # noqa: E402
from rn_forge.django.drf.views.mixins import SoftDeleteMixin  # noqa: E402
from rn_forge.django.models import (  # noqa: E402
    BaseModel,
    SoftDeleteModelMixin,
    VersionedModelMixin,
)
from rn_forge.web import MERGE_PATCH_MEDIA_TYPE, EntityVersionETagCodec  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

DELETED_AT = datetime(2026, 1, 1, tzinfo=UTC if settings.USE_TZ else None)


class _SoftNote(SoftDeleteModelMixin, VersionedModelMixin, BaseModel):
    text = models.CharField(max_length=20)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"
        verbose_name = "note"
        verbose_name_plural = "notes"


class _NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = _SoftNote
        fields = ["id", "text", "delete_time"]
        read_only_fields = ["id", "delete_time"]


class _Notes(SoftDeleteMixin, BatchDeleteMixin, BaseModelViewSet):
    # View classes bind DEFAULT_RENDERER_CLASSES at import, before WIRING applies.
    renderer_classes = [CamelCaseJSONRenderer]
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _SoftNote.objects.order_by("id")
    serializer_class = _NoteSerializer
    etag_codec = EntityVersionETagCodec()


class _StrictNotes(_Notes):
    soft_delete_requires_if_match = True


_router = CustomMethodRouter(trailing_slash=False)
_router.register("notes", _Notes, basename="notes")
_router.register("strict", _StrictNotes, basename="strict")
urlpatterns = _router.urls

WIRING = {
    "ROOT_URLCONF": __name__,
    "REST_FRAMEWORK": {
        "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
        "DEFAULT_RENDERER_CLASSES": [
            "rn_forge.django.drf.casing.CamelCaseJSONRenderer"
        ],
        "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
        "DEFAULT_SCHEMA_CLASS": "rn_forge.django.drf.openapi.WireAutoSchema",
    },
}


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_SoftNote)


@pytest.fixture
def client():
    with override_settings(**WIRING):
        yield Client(raise_request_exception=False)


def _note(text: str = "a", *, deleted: bool = False) -> _SoftNote:
    return _SoftNote.objects.create(
        text=text,
        delete_time=DELETED_AT if deleted else None,
        created_by="seed",
        updated_by="seed",
    )


def _stored(note: _SoftNote) -> _SoftNote:
    return _SoftNote.objects.get(pk=note.pk)


class TestDelete:
    def test_answers_200_with_the_resource_and_soft_deletes(self, client) -> None:
        note = _note()

        response = client.delete(f"/notes/{note.pk}")

        assert response.status_code == 200
        assert response.json()["text"] == "a"
        assert response.json()["deleteTime"] is not None
        assert response["ETag"] == f'W/"{note.pk}:2"'
        assert _stored(note).delete_time is not None

    def test_a_deleted_resource_is_404(self, client) -> None:
        note = _note(deleted=True)

        response = client.delete(f"/notes/{note.pk}")

        assert response.status_code == 404
        assert response.json()["detail"] == f"Note {note.pk} not found"

    def test_if_match_required_is_428_and_deletes_nothing(self, client) -> None:
        note = _note()

        response = client.delete(f"/strict/{note.pk}")

        assert response.status_code == 428
        assert _stored(note).delete_time is None

    def test_a_stale_if_match_is_412_and_deletes_nothing(self, client) -> None:
        note = _note()

        response = client.delete(
            f"/strict/{note.pk}", headers={"If-Match": f'W/"{note.pk}:9"'}
        )

        assert response.status_code == 412
        assert _stored(note).delete_time is None

    def test_a_current_if_match_deletes(self, client) -> None:
        note = _note()

        response = client.delete(
            f"/strict/{note.pk}", headers={"If-Match": f'W/"{note.pk}:1"'}
        )

        assert response.status_code == 200


class TestUndelete:
    def test_restores_and_answers_200_with_the_resource(self, client) -> None:
        note = _note(deleted=True)

        response = client.post(f"/notes/{note.pk}:undelete")

        assert response.status_code == 200
        assert response.json()["deleteTime"] is None
        assert response["ETag"] == f'W/"{note.pk}:2"'
        assert _stored(note).delete_time is None

    def test_a_live_resource_is_409(self, client) -> None:
        note = _note()

        response = client.post(f"/notes/{note.pk}:undelete")

        assert response.status_code == 409
        assert response.json()["detail"] == f"Note {note.pk} is not deleted"

    def test_if_match_required_is_428(self, client) -> None:
        note = _note(deleted=True)

        response = client.post(f"/strict/{note.pk}:undelete")

        assert response.status_code == 428
        assert _stored(note).delete_time is not None


class TestWrites:
    def test_put_to_a_deleted_resource_is_409(self, client) -> None:
        note = _note(deleted=True)

        response = client.put(
            f"/notes/{note.pk}",
            data=json.dumps({"text": "b"}),
            content_type="application/json",
        )

        assert response.status_code == 409
        assert response.json()["detail"] == f"Note {note.pk} is deleted"
        assert _stored(note).text == "a"

    def test_patch_to_a_deleted_resource_is_409(self, client) -> None:
        note = _note(deleted=True)

        response = client.patch(
            f"/notes/{note.pk}",
            data=json.dumps({"text": "b"}),
            content_type=MERGE_PATCH_MEDIA_TYPE,
        )

        assert response.status_code == 409

    def test_the_media_type_is_checked_before_the_state(self, client) -> None:
        note = _note(deleted=True)

        response = client.patch(
            f"/notes/{note.pk}",
            data=json.dumps({"text": "b"}),
            content_type="application/json",
        )

        assert response.status_code == 415


class TestReads:
    def test_get_returns_a_deleted_resource(self, client) -> None:
        note = _note(deleted=True)

        response = client.get(f"/notes/{note.pk}")

        assert response.status_code == 200
        assert response.json()["deleteTime"] is not None

    def test_list_omits_deleted_resources(self, client) -> None:
        live, _ = _note("live"), _note("gone", deleted=True)

        ids = [row["id"] for row in client.get("/notes").json()]

        assert live.pk in ids
        assert len(ids) == _SoftNote.objects.filter(delete_time__isnull=True).count()

    @pytest.mark.parametrize("value", ["true", "1", "TRUE"])
    def test_show_deleted_includes_them(self, client, value) -> None:
        _note("gone", deleted=True)

        rows = client.get("/notes", {"showDeleted": value}).json()

        assert len(rows) == _SoftNote.objects.count()

    @pytest.mark.parametrize("value", ["false", "0", "yes", "", "2"])
    def test_any_other_value_excludes_them(self, client, value) -> None:
        _note("gone", deleted=True)

        rows = client.get("/notes", {"showDeleted": value}).json()

        assert len(rows) == _SoftNote.objects.filter(delete_time__isnull=True).count()


class TestBatchDelete:
    def test_soft_deletes_each_row(self, client) -> None:
        first, second = _note("a"), _note("b")

        response = client.post(
            "/notes:batchDelete",
            data=json.dumps({"ids": [first.pk, second.pk]}),
            content_type="application/json",
        )

        assert response.status_code == 204
        assert _stored(first).delete_time is not None
        assert _stored(second).delete_time is not None

    def test_a_deleted_id_is_404_for_the_whole_batch(self, client) -> None:
        live, gone = _note("a"), _note("b", deleted=True)

        response = client.post(
            "/notes:batchDelete",
            data=json.dumps({"ids": [live.pk, gone.pk]}),
            content_type="application/json",
        )

        assert response.status_code == 404
        assert _stored(live).delete_time is None


@pytest.fixture(scope="module")
def schema():
    with override_settings(**WIRING):
        with patched_settings({**SPECTACULAR_SETTINGS, "TITLE": "t"}):
            return SchemaGenerator().get_schema(request=None, public=True)


class TestSchema:
    def test_undelete_is_named_and_has_no_request_body(self, schema) -> None:
        operation = schema["paths"]["/notes/{id}:undelete"]["post"]

        assert operation["operationId"] == "notesUndelete"
        assert "requestBody" not in operation
        assert "200" in operation["responses"]

    def test_the_list_documents_show_deleted(self, schema) -> None:
        names = [p["name"] for p in schema["paths"]["/notes"]["get"]["parameters"]]

        assert "showDeleted" in names

    def test_delete_is_200_with_the_resource(self, schema) -> None:
        responses = schema["paths"]["/notes/{id}"]["delete"]["responses"]

        assert "200" in responses
        assert "204" not in responses
        assert responses["200"]["content"]["application/json"]["schema"]
