# Models

## BaseModel

Nearly all concrete models should inherit from `BaseModel` (or `DateModel`/`DateRangeModel`,
which extend it):

```python
from django.db import models

from rn_forge.django.models import BaseModel


class Product(BaseModel):
    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)

    validate_on_save = True

    def natural_keys(self) -> list[str]:
        return ["sku"]
```

`BaseModel` adds:

- `status` — an `EnumField` over the `Status` enum (`Active`/`Inactive`/`Error`/`Deleted`/
  `Expired`), defaulting to `Active`
- `created_by` / `created_at` / `updated_by` / `updated_at` audit columns (snake_case Python
  fields, camelCase DB columns for legacy compatibility)
- `objects = NaturalKeyLookupManager()` — enables `get_by_natural_key()` for fixture loading,
  driven by `natural_keys()`
- `TruncateModelMixin.truncate()` — `TRUNCATE TABLE` (or `DELETE FROM` on SQLite), handy for
  test teardown
- opt-in validation-on-save: set `validate_on_save = True` to have `save()` call
  `full_clean()`; override `get_full_clean_exclude()` to control which fields are excluded on a
  partial `update_fields` save

## Date-based variants

```python
from rn_forge.django.models import DateModel, DateRangeModel


class Holiday(DateModel):
    """Adds a single `date` field."""


class Discount(DateRangeModel):
    """Adds `start_date`/`end_date` plus `is_date_range_active`."""
```

`DateRangeModel.is_date_range_active` is `True` when today falls within
`[start_date, end_date]`; an unset `end_date` means the range is open-ended.

## EnumField

```python
from django.db import models

from rn_forge.django.models import BaseEnum, EnumField


class Priority(BaseEnum):
    Low = "L"
    Medium = "M"
    High = "H"


class Task(models.Model):
    priority = EnumField.build(enum_type=Priority, default=Priority.Medium)
```

`EnumField` is a `CharField` that round-trips database values through the enum type.
`BaseEnum.get_choices()` / `BaseEnum.lookup(code)` return `{"code", "name"}` dicts, which pairs
with `EnumChoiceField` on the DRF side (see [Auth](auth.md) and [DRF Views](drf-views.md)).

## Other helpers

- `ModelUtils.as_dict(instance)` / `.to_json(instance)` — recursively serialize a model instance
  (including related objects) to JSON-safe primitives.
- `ModelLookupCache` — load a reference table once and resolve foreign keys in O(1) instead of
  per-row queries:

```python
from rn_forge.django.models import ModelLookupCache

cache = ModelLookupCache()
cache.load(Country, "iso_code")
country = cache.get(Country, "AU")
```
