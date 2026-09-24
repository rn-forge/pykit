"""The Django conformance driver: every case in `rn_forge.web.conformance.CASES`.

The fixture application is wired from this package's adapters: the problem
handler and the routing-404 handler, OpenTelemetry instrumentation, the
camelCase renderer and parser, `CursorPagination`, `CacheIdempotencyStore`,
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
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from assertpy import assert_that
from django.db import models
from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.test.client import encode_multipart
from django.urls import Resolver404, path, resolve
from import_export import fields as ie_fields
from import_export import resources as ie_resources
from import_export import widgets as ie_widgets
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.views import APIView

from rn_forge.django.auth.drf.principal import PrincipalBearerAuthentication, requires
from rn_forge.django.cors import cors_settings
from rn_forge.django.deprecation import deprecated
from rn_forge.django.drf.concurrency import enforce_version, etag_for
from rn_forge.django.drf.idempotency import CacheIdempotencyStore
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS, openapi_urlpatterns
from rn_forge.django.drf.pagination import CursorPagination
from rn_forge.django.drf.routers import CustomMethodRouter
from rn_forge.django.drf.transfer import (
    BatchCreateMixin,
    BatchDeleteMixin,
    ResourceExportMixin,
    ResourceImportMixin,
)
from rn_forge.django.security import SECURITY_SETTINGS
from rn_forge.django.tracing import instrument
from rn_forge.django.views import liveness_view, readiness_view
from rn_forge.web import (
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    Principal,
    Requirement,
    ServiceUnavailable,
    TooManyRequests,
    run_idempotent,
)
from rn_forge.web.conformance import CASES, VARIABLE_MEMBERS, case_by_id, redact

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

BOUNDARY = "conformance-boundary"
ITEM_VERSION = 7
DEPRECATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET = datetime(2026, 7, 1, tzinfo=UTC)
DEPRECATION_LINK = "https://example.com/deprecated"
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
CASING_EXEMPT = {"service-desc", "service-doc"} | set(VARIABLE_MEMBERS)
URLCONF = __name__

instrument()


class _ConformanceItem(models.Model):
    id = models.CharField(primary_key=True, max_length=10)

    class Meta:
        app_label = "rn_forge_django"


def _next_order_id():
    return str(_Order.objects.count() + 1)


class _Order(models.Model):
    id = models.CharField(primary_key=True, max_length=10, default=_next_order_id)
    name = models.CharField(max_length=20)
    quantity = models.IntegerField(default=0)

    class Meta:
        # import-export deep-copies instances, which pickles the model by an
        # installed app label.
        app_label = "rn_forge_django_messaging"
        verbose_name = "order"
        verbose_name_plural = "orders"


class _OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = _Order
        fields = ["id", "name"]
        read_only_fields = ["id"]


class _OrderExport(ie_resources.ModelResource):
    class Meta:
        model = _Order
        fields = ("id", "name")


class _WholeNumber(ie_widgets.IntegerWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            return int(value)
        except TypeError, ValueError:
            raise ValueError("Enter a whole number.") from None


class _OrderImport(ie_resources.ModelResource):
    quantity = ie_fields.Field(
        attribute="quantity", column_name="Quantity", widget=_WholeNumber()
    )

    class Meta:
        model = _Order
        fields = ("id", "name", "quantity")
        import_id_fields = ("id",)


class _Orders(
    ResourceExportMixin,
    ResourceImportMixin,
    BatchCreateMixin,
    BatchDeleteMixin,
    ModelViewSet,
):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = _Order.objects.order_by("id")
    serializer_class = _OrderSerializer
    export_resource_class = _OrderExport
    import_resource_class = _OrderImport


class _OverCap(_Orders):
    def filter_queryset(self, queryset):
        # Two rows against a cap of one, without a second row in the table
        # that the other cases count.
        rows = super().filter_queryset(queryset).order_by()
        return rows.union(rows, all=True)


_over_cap_view = _OverCap.as_view({"get": "list"})


def _over_cap(request):
    with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
        return _over_cap_view(request)


class _OrderCount(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"count": _Order.objects.count()})


_orders = CustomMethodRouter(trailing_slash=False)
_orders.register("conformance/orders", _Orders, basename="orders")


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
        # DRF's JSONParser reads via HttpRequest.read(), which Django's
        # DATA_UPLOAD_MAX_MEMORY_SIZE check does not guard (only .body does).
        _ = request.body
        serializer = _Named(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class _Item(_Open):
    def get(self, request, pk):
        row = SimpleNamespace(pk=pk, version=ITEM_VERSION)
        codec = EntityVersionETagCodec()
        response = Response({"id": pk, "version": ITEM_VERSION})
        response["ETag"] = etag_for(row, codec=codec)
        return response

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
        def execute():
            return 201, {"charged": request.data["amount"]}

        result = run_idempotent(
            _STORE,
            scope="charges",
            key=request.headers.get("Idempotency-Key"),
            method=request.method,
            body=request.data,
            execute=execute,
        )
        return Response(
            {**result.body, "replayed": result.replayed}, status=result.status
        )


class _Private(APIView):
    authentication_classes = [_Bearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"read"})))]

    def get(self, request):
        return Response({"subject": request.user.subject})


class _Echo(_Open):
    def get(self, request):
        return Response({})


class _Legacy(_Open):
    @deprecated(deprecated_at=DEPRECATED_AT, sunset=SUNSET, link=DEPRECATION_LINK)
    def get(self, request):
        return Response({"legacy": True})


class _Throttled(_Open):
    def get(self, request):
        raise TooManyRequests("Too many requests", retry_after=30)


class _Unavailable(_Open):
    def get(self, request):
        raise ServiceUnavailable("Service unavailable", retry_after=5)


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
    path("conformance/livez", liveness_view),
    path("conformance/throttled", _Throttled.as_view()),
    path("conformance/unavailable", _Unavailable.as_view()),
    path("conformance/private", _Private.as_view()),
    path("conformance/echo", _Echo.as_view()),
    path(
        "conformance/orders/named",
        _Orders.as_view({"get": "list"}, export_filename="Ordérs 2026"),
    ),
    path("conformance/orders/over-cap", _over_cap),
    path("conformance/orders/count", _OrderCount.as_view()),
    *_orders.urls,
    path("conformance/legacy", _Legacy.as_view()),
    *openapi_urlpatterns(),
]
handler404 = "rn_forge.django.exceptions.problem_details_handler404"

WIRING = {
    "ROOT_URLCONF": URLCONF,
    "INSTALLED_APPS": [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "rn_forge.django.auth",
        "rn_forge.django.messaging",
        "corsheaders",
    ],
    "MIDDLEWARE": [
        # `instrument()` (called once, above) inserts this middleware into the
        # *default* settings.MIDDLEWARE at position 0; override_settings
        # replaces the whole list, so the fixture re-declares it explicitly.
        "opentelemetry.instrumentation.django.middleware.otel_middleware._DjangoMiddleware",
        "django.middleware.http.ConditionalGetMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "rn_forge.django.security.SecurityHeadersMiddleware",
    ],
    "DATA_UPLOAD_MAX_MEMORY_SIZE": 200,
    **SECURITY_SETTINGS,
    **cors_settings(["https://example.com"]),
    "REST_FRAMEWORK": {
        "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
        "DEFAULT_RENDERER_CLASSES": [
            "rn_forge.django.drf.casing.CamelCaseJSONRenderer"
        ],
        "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
        "DEFAULT_SCHEMA_CLASS": "rn_forge.django.drf.openapi.WireAutoSchema",
    },
    "SPECTACULAR_SETTINGS": SPECTACULAR_SETTINGS,
}


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_ConformanceItem, _Order)


@pytest.fixture
def client():
    """A fresh application per case: rows reset, and the cache (the store) cleared by conftest."""
    for pk in ("1", "2", "3"):
        _ConformanceItem.objects.create(pk=pk)
    _Order.objects.create(pk="1", name="widget")
    with override_settings(**WIRING):
        yield Client(raise_request_exception=False)


def issue(client, case):
    spec = case.request
    target = f"{spec.path}?{urlencode(dict(spec.query))}" if spec.query else spec.path
    headers = dict(spec.headers)
    content_type = "application/json"
    if spec.body is None:
        data = ""
    elif headers.get("Content-Type") == "multipart/form-data":
        headers.pop("Content-Type")
        content_type = f"multipart/form-data; boundary={BOUNDARY}"
        data = encode_multipart(
            BOUNDARY, {k: ContentFile(v, name="file.csv") for k, v in spec.body.items()}
        )
    else:
        data = json.dumps(spec.body)
    return client.generic(
        spec.method, target, data=data, content_type=content_type, headers=headers
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
    for name, pattern in case.expect_header_patterns.items():
        value = response.headers.get(name)
        assert_that(value).described_as(name).is_not_none()
        assert_that(re.fullmatch(pattern, value)).described_as(
            f"{name}={value!r} ~ {pattern!r}"
        ).is_not_none()
    if case.expect_text is not None:
        assert_that(response.content.decode()).is_equal_to(case.expect_text)
        return
    body = json.loads(response.content) if response.content else {}
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
