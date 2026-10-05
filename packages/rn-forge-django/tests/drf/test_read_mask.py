from __future__ import annotations

import pytest
from django.db import models
from django.test import Client, override_settings
from rest_framework import serializers

pytest.importorskip("drf_spectacular")

from drf_spectacular.generators import SchemaGenerator  # noqa: E402
from drf_spectacular.settings import patched_settings  # noqa: E402

from rn_forge.django.drf import ReadMaskMixin  # noqa: E402
from rn_forge.django.drf.casing import CamelCaseJSONParser, CamelCaseJSONRenderer  # noqa: E402
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS  # noqa: E402
from rn_forge.django.drf.routers import CustomMethodRouter  # noqa: E402
from rn_forge.django.drf.transfer import BatchGetMixin  # noqa: E402
from rn_forge.django.drf.views.base import BaseModelViewSet  # noqa: E402
from rn_forge.django.drf.pagination import CursorPagination, OrderByFilter  # noqa: E402
from rn_forge.django.models import BaseModel, VersionedModelMixin  # noqa: E402
from rn_forge.web import EntityVersionETagCodec  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class _Contact(VersionedModelMixin, BaseModel):
    display_name = models.CharField(max_length=40)
    home_address = models.JSONField(default=dict)
    phone_numbers = models.JSONField(default=list)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"
        verbose_name_plural = "people"


class _AddressSerializer(serializers.Serializer):
    city_name = serializers.CharField()
    postcode = serializers.CharField()


class _PhoneSerializer(serializers.Serializer):
    kind = serializers.CharField()
    number = serializers.CharField()


class _ContactSerializer(serializers.ModelSerializer):
    home_address = _AddressSerializer()
    phone_numbers = _PhoneSerializer(many=True)
    secret = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = _Contact
        fields = ["id", "display_name", "home_address", "phone_numbers", "secret"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        validated_data.pop("secret", None)
        return super().create(validated_data)


class _People(BatchGetMixin, BaseModelViewSet):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _Contact.objects.order_by("id")
    serializer_class = _ContactSerializer
    # View classes bind DEFAULT_RENDERER_CLASSES at import, before WIRING applies.
    renderer_classes = [CamelCaseJSONRenderer]
    parser_classes = [CamelCaseJSONParser]
    etag_codec = EntityVersionETagCodec()


class _PagedPeople(_People):
    pagination_class = CursorPagination
    filter_backends = [OrderByFilter]
    ordering_fields = ["id"]


_router = CustomMethodRouter(trailing_slash=False)
_router.register("people", _People, basename="people")
_router.register("paged", _PagedPeople, basename="paged")
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

ADDRESS = {"city_name": "London", "postcode": "N1"}
PHONES = [{"kind": "home", "number": "1"}, {"kind": "work", "number": "2"}]


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_Contact)


@pytest.fixture
def client():
    with override_settings(**WIRING):
        yield Client(raise_request_exception=False)


@pytest.fixture
def person() -> _Contact:
    return _Contact.objects.create(
        display_name="Ada",
        home_address=ADDRESS,
        phone_numbers=PHONES,
        created_by="seed",
        updated_by="seed",
    )


def test_base_model_viewset_includes_the_mixin() -> None:
    assert issubclass(BaseModelViewSet, ReadMaskMixin)


def test_a_snake_case_field_is_selected_by_its_camel_case_path(client, person) -> None:
    response = client.get(f"/people/{person.pk}", {"readMask": "displayName"})

    assert response.status_code == 200
    assert response.json() == {"displayName": "Ada"}


def test_a_nested_snake_case_field_is_selected_by_its_camel_case_path(
    client, person
) -> None:
    response = client.get(
        f"/people/{person.pk}", {"readMask": "homeAddress.cityName,phoneNumbers.number"}
    )

    assert response.json() == {
        "homeAddress": {"cityName": "London"},
        "phoneNumbers": [{"number": "1"}, {"number": "2"}],
    }


def test_the_snake_case_spelling_is_not_a_path(client, person) -> None:
    response = client.get(f"/people/{person.pk}", {"readMask": "display_name"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown readMask path 'display_name'"


def test_a_write_only_field_cannot_be_selected(client, person) -> None:
    response = client.get(f"/people/{person.pk}", {"readMask": "secret"})

    assert response.status_code == 400


def test_a_blank_or_star_mask_returns_the_whole_resource(client, person) -> None:
    whole = client.get(f"/people/{person.pk}").json()

    assert client.get(f"/people/{person.pk}", {"readMask": ""}).json() == whole
    assert client.get(f"/people/{person.pk}", {"readMask": "*"}).json() == whole


def test_list_masks_each_element(client, person) -> None:
    response = client.get("/people", {"readMask": "displayName"})

    assert response.status_code == 200
    assert response.json() == [{"displayName": "Ada"}]


def test_a_paginated_list_masks_each_item_and_keeps_the_page_members(
    client, person
) -> None:
    response = client.get("/paged", {"readMask": "displayName"})

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"displayName": "Ada"}],
        "nextPageToken": None,
    }


def test_batch_get_masks_each_resource(client, person) -> None:
    response = client.get("/people:batchGet", {"ids": str(person.pk), "readMask": "id"})

    assert response.status_code == 200
    assert response.json() == {"people": [{"id": person.pk}]}


def test_a_masked_read_keeps_the_etag_header(client, person) -> None:
    whole = client.get(f"/people/{person.pk}")
    masked = client.get(f"/people/{person.pk}", {"readMask": "id"})

    assert masked.headers["ETag"] == whole.headers["ETag"]


def test_a_response_that_is_not_200_is_left_unmasked(client) -> None:
    response = client.get("/people/999", {"readMask": "displayName"})

    assert response.status_code == 404
    assert {"type", "title", "status", "detail"} <= set(response.json())


@pytest.mark.parametrize("raw", ["nickname", "*,id", "id,,displayName"])
def test_an_invalid_mask_is_a_400_problem(client, person, raw) -> None:
    response = client.get(f"/people/{person.pk}", {"readMask": raw})

    assert response.status_code == 400
    assert response.headers["Content-Type"] == "application/problem+json"


def test_a_write_action_ignores_the_mask(client) -> None:
    response = client.post(
        "/people?readMask=displayName",
        data={
            "displayName": "Grace",
            "homeAddress": {"cityName": "X", "postcode": "1"},
            "phoneNumbers": [],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert {"id", "displayName", "homeAddress", "phoneNumbers"} <= set(response.json())


def test_a_write_action_is_not_rejected_for_an_unknown_path(client, person) -> None:
    response = client.delete(f"/people/{person.pk}?readMask=nickname")

    assert response.status_code == 204


@pytest.fixture(scope="module")
def schema():
    # drf-spectacular caches its settings; override_settings does not reach them.
    with patched_settings({**SPECTACULAR_SETTINGS, "TITLE": "t"}):
        with override_settings(**WIRING):
            return SchemaGenerator(patterns=urlpatterns).get_schema(
                request=None, public=True
            )


def _documents_read_mask(operation) -> bool:
    return any(p["name"] == "readMask" for p in operation.get("parameters", []))


def test_the_schema_documents_read_mask_on_the_three_read_actions_only(schema) -> None:
    documented = {
        operation["operationId"]
        for item in schema["paths"].values()
        for operation in item.values()
        if _documents_read_mask(operation)
    }
    every = {
        operation["operationId"]
        for item in schema["paths"].values()
        for operation in item.values()
    }

    assert documented == {
        "peopleList",
        "peopleGet",
        "peopleBatchGet",
        "pagedList",
        "pagedGet",
        "pagedBatchGet",
    }
    assert every - documented  # writes exist and are not documented


def test_the_documented_parameter_is_an_optional_query_string(schema) -> None:
    parameter = next(
        p
        for p in schema["paths"]["/people"]["get"]["parameters"]
        if p["name"] == "readMask"
    )

    assert parameter["in"] == "query"
    assert parameter.get("required", False) is False
    assert parameter["schema"]["type"] == "string"
