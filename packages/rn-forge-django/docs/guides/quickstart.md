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

Errors as RFC 9457 problems, a correlation ID on every request, AIP-158 cursor pagination and
camelCase JSON — the same wire an `rn-forge-fastapi` service speaks:

```python
MIDDLEWARE = [
    "rn_forge.django.middleware.CorrelationIdMiddleware",  # first, so everything sees the ID
    # ... the rest of your middleware
]

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rn_forge.django.drf.pagination.CursorPagination",
    "DEFAULT_RENDERER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
}
```

And in the root URLconf:

```python
from django.urls import path
from rn_forge.django.views import healthcheck_view, readiness_view

handler404 = "rn_forge.django.exceptions.problem_details_handler404"
handler500 = "rn_forge.django.exceptions.problem_details_handler500"

urlpatterns = [
    path("healthz", healthcheck_view),
    path("readyz", readiness_view({"database": ping_database}, required=["database"])),
]
```

To give the middleware a different header, subclass it and set `header`; to send its
`request.complete` event somewhere other than `AppLogger`, override `log`.

Common imports:

```python
from rn_forge.django.models import BaseModel, DateModel, DateRangeModel, EnumField, Status
from rn_forge.django.settings import rn_forge_django_settings
from rn_forge.django.drf.views import BaseAPIView, BaseModelViewSet, ExportModelViewSet
from rn_forge.django.drf.serializers import BaseModelSerializer
```

See [Settings](settings.md), [Auth](auth.md), [DRF Views](drf-views.md), and
[Fixtures](fixtures.md) for the rest of the surface.
