# DRF Views

## Base classes

```python
from rn_forge.django.drf.views import (
    BaseAPIView,             # GenericAPIView + request-access + exception context
    BaseModelViewSet,        # ModelViewSet + audit fields + filtering + bulk create/delete
    ExportModelViewSet,      # BaseModelViewSet + export action
    UpsertImportModelViewSet,    # ExportModelViewSet + natural-key upsert import
    SnapshotImportModelViewSet,  # ExportModelViewSet + full-snapshot import (optional delete-missing)
    BulkLoadImportModelViewSet,  # ExportModelViewSet + DB-shaped bulk load import
)
```

Auth-aware equivalents that additionally enforce `AuthorizationPermission` live in
`rn_forge.django.auth.drf.views` (`AuthorizedModelViewSet`, `AuthorizedExportModelViewSet`, ...)
— see [Auth](auth.md).

## Request access and audit fields

`RequestAccessViewMixin` (included in `BaseAPIView`/`BaseModelViewSet`) exposes
`get_request_param()`, `get_request_data()`, `get_request_value()`, `get_request_user()`, and
`get_request_auth()` so views don't touch `RequestUtils` directly.

`AuditFieldsViewMixin` (included in `BaseModelViewSet`) populates `created_by`/`updated_by` from
the authenticated user's email (`"anonymous"` when unauthenticated) on `perform_create`/
`perform_update`, and on every row of a bulk create/import.

`ModelFilterViewMixin` adds default `filterset_fields` for `id`, `status`, and the audit
columns, plus an opt-in `?active=true` filter for models extending `DateRangeModel`.

## Bulk create/delete

`BaseModelViewSet` includes `bulk_create` (`POST .../bulk-create/`, body is a JSON list) and
`bulk_delete` (`DELETE .../bulk-delete/`, body is `{"ids": [...]}`). Override
`validate_bulk_create_item(item)` / `validate_bulk_delete_instance(instance)` to return an error
string and reject specific rows without failing the whole batch.

## Import/export (transfer)

Export/import/import-template actions share a `TransferColumn` list describing header ↔
serializer-field mapping:

```python
from rn_forge.django.drf.views import TransferColumn, ExportModelViewSet


class OrderViewSet(ExportModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    transfer_columns = TransferColumn.from_mapping({
        "Reference": "reference",
        "Status": "status.code",
    })
```

- `GET/POST .../export/?format=xlsx|csv|json` — respects
  `RN_FORGE_DJANGO["DRF"]["VIEWS"]["EXPORT_MAX_ROWS"]` (or `export_max_rows` on the view);
  exceeding it raises a validation error rather than truncating.
- `GET .../import-template/?format=xlsx&prefill=true` — blank or data-prefilled template using
  the same columns (prefill honors the same row limit).
- `POST .../import/?format=xlsx&dry-run=true` — uploaded `file` field (or JSON body for
  `format=json`); `dry-run=true` validates and reports counts without persisting.

Three import strategies, all subclasses of `BaseImportViewMixin`:

- **`UpsertImportViewMixin`** — natural-key lookup (`get_import_lookup_fields()`) plus
  `get_import_update_fields()`; existing rows are updated, new rows created.
- **`SnapshotImportViewMixin`** — extends upsert with `delete-missing=true` to delete existing
  rows absent from the import.
- **`BulkLoadImportViewMixin`** — DB-shaped rows keyed by primary key; skips serializer
  validation unless `validate_bulk_load_rows = True`.

Renderers/parsers are registered per format in `transfer_renderers`/`transfer_parsers`
(`csv`, `json`, `xlsx` by default) and can be swapped or extended per view.

## Serializers

```python
from rn_forge.django.drf.serializers import BaseModelSerializer


class OrderSerializer(BaseModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "reference", *BaseModelSerializer.BASE_MODEL_FIELDS]
```

`BaseModelSerializer` renders `status` through `EnumChoiceField` (`{"code", "name"}` shape) and
marks the audit columns read-only. `NestedReadPrimaryKeyRelatedField` writes by primary key but
reads through a nested serializer:

```python
from rn_forge.django.drf.serializers.fields import NestedReadPrimaryKeyRelatedField

customer = NestedReadPrimaryKeyRelatedField(
    queryset=Customer.objects.all(),
    serializer_class=CustomerSerializer,
    read_fields=["id", "name"],
)
```

## Exceptions

Register the normalized JSON exception handler in DRF settings:

```python
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.drf_exception_handler",
}
```

`ExceptionContextViewMixin` (included in the base views) supplies friendlier per-action error
messages (e.g. "Error exporting records.") consumed by that handler.
