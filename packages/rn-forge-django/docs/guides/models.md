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
- `created_by` / `create_time` / `updated_by` / `update_time` audit columns (snake_case Python
  fields and columns)
- `objects = NaturalKeyLookupManager()` — enables `get_by_natural_key()` for fixture loading,
  driven by `natural_keys()`
- `TruncateModelMixin.truncate()` — `TRUNCATE TABLE` (or `DELETE FROM` on SQLite), handy for
  test teardown
- opt-in validation-on-save: set `validate_on_save = True` to have `save()` call
  `full_clean()`; override `get_full_clean_exclude()` to control which fields are excluded on a
  partial `update_fields` save

## Concurrency and immutability

Two opt-in mixins, listed **before** the base so `BaseModel`'s validation still runs:

```python
from rn_forge.django.models import BaseModel, ImmutableModelMixin, VersionedModelMixin


class Order(VersionedModelMixin, BaseModel):
    """`version` starts at 1 and is bumped by every save of an existing row."""


class LedgerEntry(ImmutableModelMixin, BaseModel):
    """Any change outside the audit columns, and any delete, raises DomainConflict (409)."""
```

The `version` bump survives a partial `save(update_fields=[...])`. The `UPDATE` only matches the row
at the version the instance was loaded at, so a save from a stale instance — another request saved
in between — raises `rn_forge.web.VersionConflict` (412) rather than silently overwriting it. `ImmutableModelMixin` re-reads
the row on every update — one extra query — and does not guard queryset-level `update()`/`delete()`.

Turn a stale write into a 412 from a DRF view, and emit the `ETag` the client sends back:

```python
from rn_forge.django.drf import enforce_version, etag_for


def partial_update(self, request, *args, **kwargs):
    order = self.get_object()
    enforce_version(request, order, required=True)  # If-Match, or a body "version" key
    response = super().partial_update(request, *args, **kwargs)
    order.refresh_from_db()
    response["ETag"] = etag_for(order)
    return response
```

A mismatch is **412**, a missing required precondition **428**, an unparseable one **400** — decided
by `rn_forge.web.check_precondition`, not here. The body-`version` fallback is a Django-only
convenience; an API meant to be swappable with a FastAPI one should require the header.

## Generating human-readable codes

```python
from rn_forge.django.models import AbstractSequenceCounter, SequenceGenerator


class SequenceCounter(AbstractSequenceCounter):
    """Your app owns this model and its migration."""


ORDER_CODES = SequenceGenerator("order_code", counter_model=SequenceCounter, prefix="PO-")
ORDER_CODES.generate()  # "PO-000001"
ORDER_CODES.ensure_at_least(5_000)  # after an import: the next code is PO-005001
```

The counter model is abstract because this package ships no migrations; you declare the concrete
model and own its migration. A shape like `PO-2026-0001` is a `formatter=` you pass, not a default.

**What is and is not proven.** On PostgreSQL a real sequence (`nextval`) allocates the value;
elsewhere the counter row is locked with `select_for_update()`. The test suite runs on sqlite, which
has no row locks, so only the arithmetic is tested — neither the PostgreSQL path nor behaviour under
concurrent allocation is covered by this package's suite.

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
