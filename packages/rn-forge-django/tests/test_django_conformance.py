"""The Django conformance driver: every case in `rn_forge.web.conformance.CASES`.

The fixture application is wired from this package's adapters: the problem
handler and the routing-404 handler, the correlation middleware, the camelCase
renderer and parser, `CursorPagination`, `CacheIdempotencyStore`,
`enforce_version`, `readiness_view` and the principal authentication binding.
If a case needs more than a line or two over them, the adapter is missing.

Assertions are against the table, never against FastAPI's output — two stacks
agreeing on the wrong thing is not conformance.

There is no `pytest.skip` in this file, and there must never be one. A case
this stack cannot satisfy is a finding: either an adapter is missing here, or
the case encodes a decision Django cannot honour and belongs in the web plan.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from assertpy import assert_that
from django.db import models
from django.test import Client, override_settings
from django.urls import Resolver404, path, resolve
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from rn_forge.django.auth.drf.principal import PrincipalBearerAuthentication, requires
from rn_forge.django.drf.concurrency import enforce_version, etag_for
from rn_forge.django.drf.idempotency import CacheIdempotencyStore
from rn_forge.django.drf.pagination import CursorPagination
from rn_forge.django.views import readiness_view
from rn_forge.web import (
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    IdempotencyKeyRequired,
    Principal,
    Requirement,
)
from rn_forge.web.conformance import CASES, VARIABLE_MEMBERS, case_by_id, redact

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ITEM_VERSION = 7
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
CASING_EXEMPT = {"correlation_id"} | set(VARIABLE_MEMBERS)
URLCONF = __name__


class _ConformanceItem(models.Model):
    id = models.CharField(primary_key=True, max_length=10)

    class Meta:
        app_label = "rn_forge_django"


class _AnyToken:
    """Verifies every token as a principal with no scopes."""

    def authenticate(self, *, credentials):
        return Principal(subject="u1")


class _Bearer(PrincipalBearerAuthentication):
    authenticator = _AnyToken()
    realm = "conformance"


class _Open(APIView):
    authentication_classes: list = []
    permission_classes: list = []


class _Boom(_Open):
    def get(self, request):
        raise RuntimeError("connection to db-primary.internal failed: password=hunter2")


class _Conflict(_Open):
    def get(self, request):
        raise DomainConflict("Order already dispatched")


class _Named(serializers.Serializer):
    name = serializers.CharField()


class _Validate(_Open):
    def post(self, request):
        serializer = _Named(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class _Item(_Open):
    def patch(self, request, pk):
        row = SimpleNamespace(pk=pk, version=ITEM_VERSION)
        codec = EntityVersionETagCodec()
        enforce_version(request, row, required=True, codec=codec)
        response = Response({"id": pk, "version": ITEM_VERSION})
        response["ETag"] = etag_for(row, codec=codec)
        return response


class _ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = _ConformanceItem
        fields = ["id"]


class _TwoPerPage(CursorPagination):
    page_size = 2
    max_page_size = 2


class _Items(ListAPIView):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _ConformanceItem.objects.all()
    serializer_class = _ItemSerializer
    pagination_class = _TwoPerPage


_STORE = CacheIdempotencyStore()


class _Charges(_Open):
    def post(self, request):
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise IdempotencyKeyRequired("Idempotency-Key is required", error_code=400)
        stored = _STORE.record_or_replay(
            scope="charges", key=key, request_body=request.data
        )
        if stored is not None:
            return Response({**stored.body, "replayed": True}, status=stored.status)
        result = {"charged": request.data["amount"]}
        _STORE.complete(scope="charges", key=key, status=201, response_body=result)
        return Response({**result, "replayed": False}, status=201)


class _Private(APIView):
    authentication_classes = [_Bearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"read"})))]

    def get(self, request):
        return Response({"subject": request.user.subject})


class _Echo(_Open):
    def get(self, request):
        return Response({})


def _readyz(request):
    failing = request.GET.get("fail")

    def check(name):
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    return readiness_view(
        {"db": check("db"), "queue": check("queue")}, required=["db"]
    )(request)


urlpatterns = [
    path("conformance/boom", _Boom.as_view()),
    path("conformance/conflict", _Conflict.as_view()),
    path("conformance/validate", _Validate.as_view()),
    path("conformance/items/<str:pk>", _Item.as_view()),
    path("conformance/items", _Items.as_view()),
    path("conformance/charges", _Charges.as_view()),
    path("conformance/readyz", _readyz),
    path("conformance/private", _Private.as_view()),
    path("conformance/echo", _Echo.as_view()),
]
handler404 = "rn_forge.django.exceptions.problem_details_handler404"

WIRING = {
    "ROOT_URLCONF": URLCONF,
    "MIDDLEWARE": ["rn_forge.django.middleware.CorrelationIdMiddleware"],
    "REST_FRAMEWORK": {
        "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
        "DEFAULT_RENDERER_CLASSES": [
            "rn_forge.django.drf.casing.CamelCaseJSONRenderer"
        ],
        "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
    },
}


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_ConformanceItem)


@pytest.fixture
def client():
    """A fresh application per case: rows reset, and the cache (the store) cleared by conftest."""
    for pk in ("1", "2", "3"):
        _ConformanceItem.objects.create(pk=pk)
    with override_settings(**WIRING):
        yield Client(raise_request_exception=False)


def issue(client, case):
    spec = case.request
    target = f"{spec.path}?{urlencode(dict(spec.query))}" if spec.query else spec.path
    return client.generic(
        spec.method,
        target,
        data=json.dumps(spec.body) if spec.body is not None else "",
        content_type="application/json",
        headers=dict(spec.headers),
    )


def casing_violations(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key not in CASING_EXEMPT and not CAMEL_CASE.match(key):
                found.append(key)
            casing_violations(value, found)
    elif isinstance(node, list):
        for item in node:
            casing_violations(item, found)
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_django_conforms(client, case):
    for prerequisite in case.depends_on:
        issue(client, case_by_id(prerequisite))

    response = issue(client, case)

    assert_that(response.status_code).described_as("status").is_equal_to(
        case.expect_status
    )
    for name, value in case.expect_headers.items():
        assert_that(response.headers.get(name)).described_as(name).is_equal_to(value)
    for name in case.expect_absent_headers:
        assert_that(name in response.headers).described_as(name).is_false()
    body = json.loads(response.content)
    assert_that(redact(body)).is_equal_to(dict(case.expect_body))
    assert_that(casing_violations(body)).described_as("camelCase").is_empty()


def test_the_fixture_serves_every_path_the_table_uses():
    """A case added for an endpoint this driver does not serve must fail here."""
    unserved = set()
    for case in CASES:
        if case.request.path == "/conformance/missing":
            continue
        try:
            resolve(case.request.path, urlconf=URLCONF)
        except Resolver404:
            unserved.add(case.request.path)
    assert_that(unserved).is_empty()


def test_missing_really_is_unrouted():
    with pytest.raises(Resolver404):
        resolve("/conformance/missing", urlconf=URLCONF)
