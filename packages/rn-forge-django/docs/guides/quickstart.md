# Quickstart

```python
from django.db import models

from rn_forge.django.models import BaseModel, EnumField, Status


class Order(BaseModel):
    reference = models.CharField(max_length=64, unique=True)

    def natural_keys(self) -> list[str]:
        return ["reference"]
```

`BaseModel` adds `status`, `created_by`/`created_at`/`updated_by`/`updated_at`, and a
`NaturalKeyLookupManager` default manager — see [Models](models.md).

Wire a DRF viewset over it:

```python
from rest_framework import serializers

from rn_forge.django.drf.serializers import BaseModelSerializer
from rn_forge.django.drf.views import BaseModelViewSet


class OrderSerializer(BaseModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "reference", *BaseModelSerializer.BASE_MODEL_FIELDS]


class OrderViewSet(BaseModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
```

## Wire it to the shared API contract

Errors as RFC 9457 problems, W3C Trace Context on every request, AIP-158 cursor pagination and
camelCase JSON — the same wire an `rn-forge-fastapi` service speaks:

```python
# manage.py, wsgi.py, asgi.py — before Django loads
from rn_forge.django.tracing import instrument  # the `otel` extra

instrument()
```

```python
from rn_forge.django.security import SECURITY_SETTINGS

MIDDLEWARE = [
    # DjangoInstrumentor (from instrument(), above) inserts its own middleware
    # at position 0 here, ahead of everything below.
    "django.middleware.http.ConditionalGetMiddleware",  # If-None-Match -> 304 on any ETag response
    "django.middleware.security.SecurityMiddleware",  # nosniff, Referrer-Policy, X-Frame-Options, HSTS
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "rn_forge.django.security.SecurityHeadersMiddleware",  # Cache-Control, CSP frame-ancestors
    # ... the rest of your middleware
]

globals().update(SECURITY_SETTINGS)  # or assign SECURE_CONTENT_TYPE_NOSNIFF etc. yourself
```

### CORS

Opt-in (the `cors` extra, `django-cors-headers`), and the application owns the origins:

```python
from rn_forge.django.cors import cors_settings

INSTALLED_APPS = [
    "corsheaders",
    # ...
]
MIDDLEWARE = [
    # ... CorsMiddleware goes above CommonMiddleware, if you use one
    "corsheaders.middleware.CorsMiddleware",
    # ...
]
globals().update(cors_settings(["https://app.example.com"]))

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rn_forge.django.drf.pagination.CursorPagination",
    "DEFAULT_RENDERER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
}
```

And in the root URLconf:

```python
from rn_forge.django.views import health_urlpatterns

handler404 = "rn_forge.django.exceptions.problem_details_handler404"
handler500 = "rn_forge.django.exceptions.problem_details_handler500"

urlpatterns = [
    *health_urlpatterns(checks={"database": ping_database}, required=["database"]),
]
```

`health_urlpatterns` serves `/livez` (liveness), `/readyz` (readiness) and `/healthz` (a
deprecated alias of `/livez`), each with no trailing slash — a probe on every host fails on a
redirect, and `APPEND_SLASH` would send one.

With the `otel` extra and `instrument()`, the request span is the access record: method, path,
status and duration.

### Deprecating a view

```python
from datetime import UTC, datetime

from drf_spectacular.utils import extend_schema
from rn_forge.django.deprecation import deprecated

SUNSET_ANNOUNCED = datetime(2026, 1, 1, tzinfo=UTC)
SUNSET_DATE = datetime(2026, 7, 1, tzinfo=UTC)


class LegacySummaryView(APIView):
    @extend_schema(deprecated=True)  # marks the OpenAPI operation
    @deprecated(deprecated_at=SUNSET_ANNOUNCED, sunset=SUNSET_DATE)
    def get(self, request): ...
```

`@extend_schema(deprecated=True)` and `@deprecated(...)` are both needed: one marks the
document, the other stamps the `Deprecation`/`Sunset`/`Link` headers on the wire (RFC 9745,
RFC 8594).

Common imports:

```python
from rn_forge.django.models import BaseModel, DateModel, DateRangeModel, EnumField, Status
from rn_forge.django.settings import rn_forge_django_settings
from rn_forge.django.drf.views import BaseAPIView, BaseModelViewSet, ExportModelViewSet
from rn_forge.django.drf.serializers import BaseModelSerializer
```

See [Settings](settings.md), [Auth](auth.md), [DRF Views](drf-views.md), and
[Fixtures](fixtures.md) for the rest of the surface.

`rn-forge-web`'s "Deployment" guide maps `/livez`, `/readyz`, the security headers' `hsts`
setting, CORS and body-size limits onto Kubernetes, App Engine and Azure App Service.
