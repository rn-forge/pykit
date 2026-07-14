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

Common imports:

```python
from rn_forge.django.models import BaseModel, DateModel, DateRangeModel, EnumField, Status
from rn_forge.django.settings import rn_forge_django_settings
from rn_forge.django.drf.views import BaseAPIView, BaseModelViewSet, ExportModelViewSet
from rn_forge.django.drf.serializers import BaseModelSerializer
```

See [Settings](settings.md), [Auth](auth.md), [DRF Views](drf-views.md), and
[Fixtures](fixtures.md) for the rest of the surface.
