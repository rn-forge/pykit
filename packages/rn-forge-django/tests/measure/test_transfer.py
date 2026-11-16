"""Measure query and memory costs for the transfer mixins."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import ClassVar

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
    ),
]

pytest.importorskip("import_export")

from django.db import connection, models
from django.test import override_settings
from import_export import fields, resources
from rest_framework import serializers
from rest_framework.viewsets import ModelViewSet
from rn_forge.django.drf.routers import CustomMethodRouter
from rn_forge.django.drf.transfer import (
    BatchCreateMixin,
    BatchDeleteMixin,
    BatchGetMixin,
    BatchUpdateMixin,
    ResourceExportMixin,
)
from rn_forge.django.drf.views.base import BaseModelViewSet
from rn_forge.django.models import BaseModel, VersionedModelMixin

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


class MeasureTeam(models.Model):
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        app_label = "rn_forge_django_messaging"


class MeasureMember(models.Model):
    name = models.CharField(max_length=30)
    email = models.CharField(max_length=50, unique=True)
    team = models.ForeignKey(
        MeasureTeam, null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        app_label = "rn_forge_django_messaging"


class MeasureBook(VersionedModelMixin, BaseModel):
    name = models.CharField(max_length=30)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django_messaging"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(MeasureTeam, MeasureMember, MeasureBook)


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasureMember
        fields: ClassVar = ["id", "name", "email"]


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasureBook
        fields: ClassVar = ["id", "name"]
        read_only_fields: ClassVar = ["id"]


class MemberExport(resources.ModelResource):
    email = fields.Field(attribute="email", column_name="Email")
    team = fields.Field(attribute="team__code", column_name="Team")

    class Meta:
        model = MeasureMember
        fields = ("email", "team")
        export_order = fields


class Members(ResourceExportMixin, BatchCreateMixin, BatchDeleteMixin, ModelViewSet):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = []
    queryset = MeasureMember.objects.select_related("team").order_by("id")
    serializer_class = MemberSerializer
    export_resource_class = MemberExport


class Books(BatchGetMixin, BatchUpdateMixin, BaseModelViewSet):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = []
    queryset = MeasureBook.objects.order_by("id")
    serializer_class = BookSerializer


router = CustomMethodRouter(trailing_slash=False)
router.register("members", Members, basename="members")
router.register("books", Books, basename="books")
urlpatterns = router.urls


@pytest.fixture(autouse=True)
def _urlconf():
    with override_settings(
        ROOT_URLCONF=__name__,
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
        },
    ):
        yield


def _post(client, path, body):
    return client.post(path, json.dumps(body), content_type="application/json")


@pytest.mark.parametrize(
    "op", ["export", "batch_get", "batch_create", "batch_update", "batch_delete"]
)
def test_transfer_measurements(client, measure: Measure, op: str) -> None:
    def request(rows: int, call, expected_status: int = 200) -> int:
        queries = 0

        def count_queries(execute, sql, params, many, context):
            nonlocal queries
            queries += 1
            return execute(sql, params, many, context)

        with measure(
            "django_transfer",
            {"op": op, "rows": rows, "dialect": connection.vendor},
            "io",
        ) as counts:
            with connection.execute_wrapper(count_queries):
                response = call()
            assert response.status_code == expected_status
            counts["queries"] = queries
            counts["response_bytes"] = len(response.content)
        return queries

    if op == "export":
        team = MeasureTeam.objects.create(code="EAST")
        MeasureMember.objects.bulk_create(
            MeasureMember(name=f"n{i}", email=f"e{i}@x.io", team=team)
            for i in range(1_000)
        )
        small = request(
            1_000, lambda: client.get("/members", headers={"Accept": "text/csv"})
        )
        MeasureMember.objects.bulk_create(
            MeasureMember(name=f"n{i}", email=f"e{i}@x.io", team=team)
            for i in range(1_000, 9_000)
        )
        large = request(
            9_000, lambda: client.get("/members", headers={"Accept": "text/csv"})
        )
        assert large == small
    elif op == "batch_get":
        MeasureBook.objects.bulk_create(MeasureBook(name=f"b{i}") for i in range(900))
        ids = list(MeasureBook.objects.order_by("id").values_list("id", flat=True))
        small = request(100, lambda: client.get("/books:batchGet", {"ids": ids[:100]}))
        large = request(900, lambda: client.get("/books:batchGet", {"ids": ids}))
        assert large == small
    elif op == "batch_create":

        def create(count: int):
            items = [
                {"name": f"n{i}", "email": f"c{count}-{i}@x.io"} for i in range(count)
            ]
            return _post(client, "/members:batchCreate", {"requests": items})

        small = request(100, lambda: create(100))
        large = request(900, lambda: create(900))
        assert large - small == 2 * (900 - 100)
    elif op == "batch_update":
        MeasureBook.objects.bulk_create(MeasureBook(name=f"b{i}") for i in range(900))
        ids = list(MeasureBook.objects.order_by("id").values_list("id", flat=True))

        def update(chosen):
            return _post(
                client,
                "/books:batchUpdate",
                {
                    "requests": [
                        {"id": str(pk), "patch": {"name": "z"}} for pk in chosen
                    ]
                },
            )

        small = request(100, lambda: update(ids[:100]))
        large = request(900, lambda: update(ids))
        assert large - small == 900 - 100
    else:
        MeasureMember.objects.bulk_create(
            MeasureMember(name=f"n{i}", email=f"e{i}@x.io") for i in range(1_000)
        )
        ids = list(MeasureMember.objects.order_by("id").values_list("id", flat=True))
        small = request(
            100, lambda: _post(client, "/members:batchDelete", {"ids": ids[:100]}), 204
        )
        large = request(
            900, lambda: _post(client, "/members:batchDelete", {"ids": ids[100:]}), 204
        )
        assert large - small == 900 - 100
