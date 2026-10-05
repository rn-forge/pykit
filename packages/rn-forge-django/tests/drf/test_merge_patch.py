from __future__ import annotations

import json

import pytest
from django.db import models
from django.test import Client, override_settings
from django.urls import include, path
from rest_framework import serializers
from rest_framework.routers import SimpleRouter

pytest.importorskip("drf_spectacular")

from drf_spectacular.generators import SchemaGenerator  # noqa: E402
from drf_spectacular.settings import patched_settings  # noqa: E402

from rn_forge.django.drf import MergePatchMixin, MergePatchParser  # noqa: E402
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS  # noqa: E402
from rn_forge.django.drf.views.base import BaseModelViewSet  # noqa: E402
from rn_forge.django.models import BaseModel, VersionedModelMixin  # noqa: E402
from rn_forge.web import (  # noqa: E402
    MERGE_PATCH_MEDIA_TYPE,
    EntityVersionETagCodec,
    NULL_FIELD_DETAIL,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

JSON = "application/json"


class _Document(VersionedModelMixin, BaseModel):
    name = models.CharField(max_length=40)
    note = models.CharField(max_length=40, null=True, blank=True)
    tags = models.JSONField(default=list)
    settings = models.JSONField(default=dict)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"


class _Plain(BaseModel):
    name = models.CharField(max_length=40)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"


class _DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = _Document
        fields = ["id", "name", "note", "tags", "settings", "version", "updated_by"]
        read_only_fields = ["id", "version", "updated_by"]


class _PlainSerializer(serializers.ModelSerializer):
    class Meta:
        model = _Plain
        fields = ["id", "name"]
        read_only_fields = ["id"]


class _Documents(BaseModelViewSet):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _Document.objects.all()
    serializer_class = _DocumentSerializer


class _StrictDocuments(_Documents):
    merge_patch_requires_if_match = True
    etag_codec = EntityVersionETagCodec()


class _Plains(BaseModelViewSet):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _Plain.objects.all()
    serializer_class = _PlainSerializer


_router = SimpleRouter()
_router.register("documents", _Documents, basename="document")
_router.register("strict", _StrictDocuments, basename="strict")
_router.register("plains", _Plains, basename="plain")
urlpatterns = [path("", include(_router.urls))]

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
    create_tables(_Document, _Plain)


@pytest.fixture
def client():
    with override_settings(**WIRING):
        yield Client(raise_request_exception=False)


@pytest.fixture
def document() -> _Document:
    return _Document.objects.create(
        name="widget",
        note="fragile",
        tags=["a", "b"],
        settings={"color": "red", "size": "L"},
        created_by="seed",
        updated_by="seed",
    )


def patch(client, url, body, content_type=MERGE_PATCH_MEDIA_TYPE, **headers):
    data = body if isinstance(body, str) else json.dumps(body)
    return client.patch(url, data=data, content_type=content_type, headers=headers)


class TestParsers:
    def test_patch_gets_only_the_merge_patch_parser(self) -> None:
        view = _Documents()
        view.request = type("R", (), {"method": "PATCH"})()
        assert [type(p) for p in view.get_parsers()] == [MergePatchParser]

    @pytest.mark.parametrize("method", ["PUT", "POST"])
    def test_other_methods_keep_the_view_parsers(self, method) -> None:
        view = _Documents()
        view.request = type("R", (), {"method": method})()
        parsers = view.get_parsers()
        assert parsers
        assert MergePatchParser not in {type(p) for p in parsers}

    def test_mixin_is_part_of_the_base_viewset(self) -> None:
        assert issubclass(BaseModelViewSet, MergePatchMixin)
        assert MergePatchParser.media_type == MERGE_PATCH_MEDIA_TYPE


class TestMediaType:
    def test_json_is_415_with_accept_patch(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"name": "x"}, JSON)
        assert response.status_code == 415
        assert response["Accept-Patch"] == MERGE_PATCH_MEDIA_TYPE
        assert response.json()["detail"] == (
            "Use Content-Type: application/merge-patch+json for PATCH"
        )

    def test_parameters_are_ignored(self, client, document) -> None:
        response = patch(
            client,
            f"/documents/{document.pk}/",
            {"name": "x"},
            f"{MERGE_PATCH_MEDIA_TYPE}; charset=utf-8",
        )
        assert response.status_code == 200

    def test_media_type_is_checked_before_the_body_is_read(
        self, client, document
    ) -> None:
        response = patch(client, f"/documents/{document.pk}/", "{not json", JSON)
        assert response.status_code == 415

    def test_media_type_is_checked_before_the_precondition(
        self, client, document
    ) -> None:
        response = patch(
            client,
            f"/strict/{document.pk}/",
            {"name": "x"},
            JSON,
            **{"If-Match": 'W/"9"'},
        )
        assert response.status_code == 415

    def test_put_refuses_the_merge_patch_media_type(self, client, document) -> None:
        response = client.put(
            f"/documents/{document.pk}/",
            data=json.dumps({"name": "x"}),
            content_type=MERGE_PATCH_MEDIA_TYPE,
        )
        assert response.status_code == 415

    def test_put_still_takes_json(self, client, document) -> None:
        response = client.put(
            f"/documents/{document.pk}/",
            data=json.dumps({"name": "x"}),
            content_type=JSON,
        )
        assert response.status_code == 200


class TestPrecondition:
    def test_required_and_absent_is_428(self, client, document) -> None:
        response = patch(client, f"/strict/{document.pk}/", {"name": "x"})
        assert response.status_code == 428

    def test_malformed_is_400(self, client, document) -> None:
        response = patch(
            client, f"/documents/{document.pk}/", {"name": "x"}, **{"If-Match": "1"}
        )
        assert response.status_code == 400

    def test_stale_is_412_and_changes_nothing(self, client, document) -> None:
        response = patch(
            client, f"/documents/{document.pk}/", {"name": "x"}, **{"If-Match": 'W/"9"'}
        )
        assert response.status_code == 412
        document.refresh_from_db()
        assert document.name == "widget"

    def test_precondition_is_checked_before_the_body(self, client, document) -> None:
        response = patch(
            client, f"/documents/{document.pk}/", ["x"], **{"If-Match": 'W/"9"'}
        )
        assert response.status_code == 412

    def test_matching_entity_etag_passes(self, client, document) -> None:
        etag = client.get(f"/strict/{document.pk}/")["ETag"]
        response = patch(
            client, f"/strict/{document.pk}/", {"name": "x"}, **{"If-Match": etag}
        )
        assert response.status_code == 200
        assert response["ETag"] == f'W/"{document.pk}:2"'

    def test_unversioned_instance_needs_no_precondition(self, client) -> None:
        plain = _Plain.objects.create(name="a", created_by="t", updated_by="t")
        response = patch(client, f"/plains/{plain.pk}/", {"name": "b"})
        assert response.status_code == 200
        assert "ETag" not in response
        assert response.json()["name"] == "b"


class TestBody:
    @pytest.mark.parametrize("body", [["name"], '"name"', "null", "1"])
    def test_non_object_is_422(self, client, document, body) -> None:
        response = patch(client, f"/documents/{document.pk}/", body)
        assert response.status_code == 422
        assert response.json()["detail"] == "A merge patch must be a JSON object."

    def test_null_on_a_non_nullable_field_is_422(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"name": None})
        assert response.status_code == 422
        body = response.json()
        assert body["detail"] == "Validation Error"
        assert body["errors"] == [{"pointer": "/name", "detail": NULL_FIELD_DETAIL}]
        document.refresh_from_db()
        assert document.name == "widget"

    def test_null_sets_a_nullable_field_to_null(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"note": None})
        assert response.status_code == 200
        assert response.json()["note"] is None
        document.refresh_from_db()
        assert document.note is None

    def test_nested_merge_keeps_absent_members(self, client, document) -> None:
        response = patch(
            client, f"/documents/{document.pk}/", {"settings": {"color": "blue"}}
        )
        assert response.json()["settings"] == {"color": "blue", "size": "L"}
        assert response.json()["name"] == "widget"

    def test_null_inside_a_json_value_removes_the_member(
        self, client, document
    ) -> None:
        response = patch(
            client, f"/documents/{document.pk}/", {"settings": {"size": None}}
        )
        assert response.json()["settings"] == {"color": "red"}

    def test_array_is_replaced_whole(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"tags": ["c"]})
        assert response.json()["tags"] == ["c"]

    def test_read_only_and_unknown_members_are_ignored(self, client, document) -> None:
        response = patch(
            client,
            f"/documents/{document.pk}/",
            {"id": 99, "updatedBy": "x", "bogus": 1, "name": "gadget"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == document.pk
        assert body["name"] == "gadget"
        assert body["version"] == 2


class TestEtag:
    def test_retrieve_answers_an_etag(self, client, document) -> None:
        response = client.get(f"/documents/{document.pk}/")
        assert response.status_code == 200
        assert response["ETag"] == 'W/"1"'

    def test_patch_answers_the_new_etag(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"name": "x"})
        assert response["ETag"] == 'W/"2"'

    def test_read_then_if_match_round_trips(self, client, document) -> None:
        etag = client.get(f"/documents/{document.pk}/")["ETag"]
        first = patch(
            client, f"/documents/{document.pk}/", {"name": "x"}, **{"If-Match": etag}
        )
        assert first.status_code == 200
        second = patch(
            client, f"/documents/{document.pk}/", {"name": "y"}, **{"If-Match": etag}
        )
        assert second.status_code == 412


class TestAuditFields:
    def test_perform_update_still_sets_the_audit_fields(self, client, document) -> None:
        response = patch(client, f"/documents/{document.pk}/", {"name": "x"})
        assert response.status_code == 200
        document.refresh_from_db()
        assert document.updated_by == "anonymous"
        assert document.created_by == "seed"


def test_openapi_lists_only_the_merge_patch_media_type() -> None:
    with patched_settings({**SPECTACULAR_SETTINGS, "TITLE": "t"}):
        with override_settings(**WIRING):
            schema = SchemaGenerator(patterns=urlpatterns).get_schema(
                request=None, public=True
            )
    operations = schema["paths"]["/documents/{id}/"]
    assert set(operations["patch"]["requestBody"]["content"]) == {
        MERGE_PATCH_MEDIA_TYPE
    }
    assert JSON in operations["put"]["requestBody"]["content"]
    assert MERGE_PATCH_MEDIA_TYPE not in operations["put"]["requestBody"]["content"]
