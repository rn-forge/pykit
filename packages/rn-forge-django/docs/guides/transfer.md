# Transfer: export, import and batch operations

`rn_forge.django.drf.transfer` needs the `transfer` extra (`django-import-export[xlsx]`, which
brings `tablib` and `openpyxl`). It is not imported by `rn_forge.django.drf`, so a project that
does not use it installs neither. Register viewsets with `CustomMethodRouter` so the extra
actions are served as `/orders:import` and `/orders:batchCreate` (AIP-136), not `/orders/import`.

```python
from import_export import fields, resources, widgets
from rest_framework.viewsets import ModelViewSet

from rn_forge.django.drf.routers import CustomMethodRouter
from rn_forge.django.drf.transfer import (
    BatchCreateMixin, BatchDeleteMixin, ResourceExportMixin, ResourceImportMixin,
)


class OrderExport(resources.ModelResource):
    store = fields.Field(attribute="store__sap", column_name="Store")

    class Meta:
        model = Order
        fields = ("reference", "store", "quantity")


class OrderImport(resources.ModelResource):
    reference = fields.Field(attribute="reference", column_name="REF")
    store = fields.Field(
        attribute="store", column_name="STORE",
        widget=widgets.ForeignKeyWidget(Store, field="sap"),
    )

    class Meta:
        model = Order
        fields = ("reference", "store")
        import_id_fields = ("reference",)
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        user = kwargs["user"]  # the request user: set audit fields, authorize the row


class OrderViewSet(
    ResourceExportMixin, ResourceImportMixin, BatchCreateMixin, BatchDeleteMixin, ModelViewSet
):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    export_resource_class = OrderExport
    import_resource_class = OrderImport
    export_column_formats = {"Quantity": "#,##0"}


router = CustomMethodRouter(trailing_slash=False)
router.register("orders", OrderViewSet, basename="orders")
```

A viewset takes only the mixins it needs. The wire shapes are those of the transfer section of
the `rn-forge-web` API conventions.

| Request | Behaviour |
| --- | --- |
| `GET /orders` with `Accept: text/csv` or the XLSX media type, or `?format=csv\|xlsx` | The JSON list's filters, then `Resource.export()`; not paginated. Above `transfer.max_rows` it is a 422 problem naming the cap. `Content-Disposition` carries `filename*`. Permission is that of `list`. |
| `POST /orders:import`, `multipart/form-data` `file`, `?validateOnly=true` | Upsert through the import resource. `200 {created, updated, skipped, validateOnly}`; any row error is a 422 with `errors[].pointer = "/rows/<row>/<column>"` and nothing persisted. Permission `upload`. |
| `GET /orders:importTemplate`, `?prefill=true` | The import columns, negotiated like an export; prefill adds the filtered rows. |
| `POST /orders:batchCreate`, `{"requests": [...]}` | Each item through the serializer, all or nothing. `200 {"orders": [...]}`. |
| `POST /orders:batchDelete`, `{"ids": [...]}` | All or nothing, `204`. An id outside the filtered queryset is a 404 naming it. |

Row numbers in pointers count from 0. A pointer names the column as it appears in the file when
the failing field is an import field. An error `import-export` raises outside field validation
(a `ForeignKeyWidget` that finds no row, or an exception in `before_import_row`) points at the
whole row.

## Per-item authorization

Override the hooks and return a message to refuse an item; the response is one 403 problem with
`errors[].pointer` naming the item, and nothing is persisted.

- `prepare_batch_create_item(item)` runs on each raw item before validation.
- `validate_batch_create_item(item)` runs on each validated item, after
  `AuditFieldsViewMixin.prepare_create_data`.
- `validate_batch_delete_instance(instance)` runs on each instance to delete.

In an import resource the same check belongs in `before_import_row(row, **kwargs)`, where
`kwargs["user"]` is the request user; raising there is reported as a row error.

## Committing the valid rows

Set `import_rollback_on_validation_errors = False` on the viewset to commit the valid rows when
the only failures are field validation errors. The response is `200` with the failures under
`errors`. Any other error still rolls the import back.

## Settings

`RN_FORGE_DJANGO["DRF"]["TRANSFER"]["MAX_ROWS"]` (default 10 000, `None` for no cap) limits the
rows of an export or import and the items of a batch request.

## Migrating from `ew-loop-api`

The application moves when it adopts pykit; nothing here gates pykit.

| `ew-loop-api` | Now |
| --- | --- |
| `_get_download_template` / `_build_download_template_row` | An export `Resource`: `Field(attribute="store__sap", column_name="Store")`, `dehydrate_<field>` for computed columns and enum display names, `export_column_formats` for dates and currency |
| `_get_upload_template` / `_build_instance` / `_build_foreignkey_lookups` | An import `Resource`: `import_id_fields`, `ForeignKeyWidget(Role, field="code")`, `before_import_row` for normalization and per-row authorization, `skip_unchanged` with explicit `fields` |
| `POST .../download` with base64 CSV in a JSON body | `GET` with `Accept: text/csv` or the XLSX media type, or `?format=` on a link |
| `POST .../upload` with simulation mode | `POST /orders:import` with `?validateOnly=true` |
| Commit valid rows, report the rest | `import_rollback_on_validation_errors = False` |
| Bulk create (`POST` of a JSON list) and bulk delete (`DELETE` with ids), on hyphenated sub-paths | `POST /orders:batchCreate` with `{"requests": [...]}`; `POST /orders:batchDelete` with `{"ids": [...]}` |
| Row errors joined with `"\n"` into a 403 | 403 or 422 problem, one `errors[]` entry per item |
| Bespoke report workbooks | Build the workbook in a service and return it with `content_disposition` from `rn_forge.web` |
