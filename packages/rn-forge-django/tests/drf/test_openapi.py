from __future__ import annotations

import pytest

pytest.importorskip("drf_spectacular")

from django.urls import path  # noqa: E402
from drf_spectacular.generators import SchemaGenerator  # noqa: E402
from drf_spectacular.settings import patched_settings  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.generics import GenericAPIView  # noqa: E402
from rest_framework.response import Response  # noqa: E402

from rn_forge.django.auth.drf.principal import (  # noqa: E402
    PrincipalBearerAuthentication,
    requires,
)
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS, WireAutoSchema  # noqa: E402
from rn_forge.django.drf.serializers import HealthReportSerializer  # noqa: E402
from rn_forge.web import Requirement  # noqa: E402

pytestmark = pytest.mark.unit


class _WorkItemSerializer(serializers.Serializer):
    work_item_id = serializers.CharField()
    due_date = serializers.DateField(required=False)


class _Bearer(PrincipalBearerAuthentication):
    authenticator = None


class _Base(GenericAPIView):
    schema = WireAutoSchema()
    authentication_classes: list = []
    permission_classes: list = []
    serializer_class = _WorkItemSerializer


class _CollectionView(_Base):
    authentication_classes = [_Bearer]
    permission_classes = [requires(Requirement())]

    def get(self, request):
        return Response([])

    def post(self, request):
        return Response({})


class _ItemView(_Base):
    def get(self, request, pk):
        return Response({})

    def patch(self, request, pk):
        return Response({})

    def delete(self, request, pk):
        return Response(status=204)


class _ReadyView(_Base):
    serializer_class = HealthReportSerializer

    def get(self, request):
        return Response({})


urlpatterns = [
    path("api/work-items", _CollectionView.as_view()),
    path("api/work-items/<str:pk>", _ItemView.as_view()),
    path("readyz", _ReadyView.as_view()),
]


@pytest.fixture(scope="module")
def schema():
    # drf-spectacular caches its settings; override_settings does not reach them.
    with patched_settings({**SPECTACULAR_SETTINGS, "TITLE": "t"}):
        return SchemaGenerator(patterns=urlpatterns).get_schema(
            request=None, public=True
        )


def _operation_ids(schema) -> set[str]:
    return {
        op["operationId"] for item in schema["paths"].values() for op in item.values()
    }


def test_openapi_version_is_3_1_0(schema) -> None:
    assert schema["openapi"] == "3.1.0"


def test_problem_detail_component_is_always_present(schema) -> None:
    assert set(schema["components"]["schemas"]["ProblemDetail"]["required"]) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
    }


def test_shared_component_names(schema) -> None:
    assert {"HealthReport", "CheckResult"} <= set(schema["components"]["schemas"])


def test_operation_ids_follow_the_resource_verb_convention(schema) -> None:
    assert _operation_ids(schema) >= {
        "workItemsList",
        "workItemsCreate",
        "workItemsGet",
        "workItemsUpdate",
        "workItemsDelete",
        "readyzList",
    }


def test_component_properties_are_camel_case(schema) -> None:
    component = schema["components"]["schemas"]["_WorkItem"]
    assert set(component["properties"]) == {"workItemId", "dueDate"}
    assert component["required"] == ["workItemId"]


def test_bearer_security_scheme_is_declared(schema) -> None:
    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
