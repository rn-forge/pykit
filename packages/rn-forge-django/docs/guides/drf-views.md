# DRF Views

## Base classes

```python
from rn_forge.django.drf.views import (
    BaseAPIView,             # GenericAPIView + request-access + exception context
    BaseModelViewSet,        # ModelViewSet + audit fields + filtering
)
```

Auth-aware equivalents that additionally enforce `AuthorizationPermission` live in
`rn_forge.django.auth.drf.views` (`AuthorizedModelViewSet`, `AuthorizedAPIView`)
— see [Auth](auth.md).

## Request access and audit fields

`RequestAccessViewMixin` (included in `BaseAPIView`/`BaseModelViewSet`) exposes
`get_request_param()`, `get_request_data()`, `get_request_value()`, `get_request_user()`, and
`get_request_auth()` so views don't touch `RequestUtils` directly.

`AuditFieldsViewMixin` (included in `BaseModelViewSet`) populates `created_by`/`updated_by` from
the authenticated user's email (`"anonymous"` when unauthenticated) on `perform_create`/
`perform_update`, and on every item of a batch create.

`ModelFilterViewMixin` adds default `filterset_fields` for `id`, `status`, and the audit
columns, plus an opt-in `?active=true` filter for models extending `DateRangeModel`.

## Merge patch

`BaseModelViewSet` includes `MergePatchMixin`: its `PATCH` takes `application/merge-patch+json`
(RFC 7396) and answers any other media type with 415 and `Accept-Patch`. `PUT` and `POST` still
take `application/json`. The merged document is validated as a full update. See the API
conventions, section 10, in `rn-forge-web` for the request order and the `null` rule.

A versioned model (`VersionedModelMixin`) checks `If-Match`, and `retrieve` and `PATCH` answer with
an `ETag`. Set `etag_codec`, and `merge_patch_requires_if_match = True` to make the header
required (428 when absent).

```python
from rn_forge.django.drf.views import BaseModelViewSet
from rn_forge.web import EntityVersionETagCodec


class DocumentViewSet(BaseModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    etag_codec = EntityVersionETagCodec()
    merge_patch_requires_if_match = True
```

```http
PATCH /documents/1
Content-Type: application/merge-patch+json
If-Match: W/"1:1"

{"settings": {"size": null}, "note": null}
```

A view outside `BaseModelViewSet` adds `MergePatchMixin` from `rn_forge.django.drf`.

## Partial responses

`BaseModelViewSet` includes `ReadMaskMixin`: `retrieve`, `list` and `batch_get` accept `readMask`
and answer `200` with only the fields it names. Fields are selected by their camelCase wire names
as the view's serializer declares them: a nested serializer or a list serializer can be reached
with a dotted path, any other field (a `JSONField` included) is a leaf, and a write-only field
cannot be selected. A path that names nothing is a 400 problem. See the API conventions, section
20, in `rn-forge-web` for the rules.

```http
GET /profiles/1?readMask=displayName,address.city
```

```json
{"displayName": "Ada", "address": {"city": "London"}}
```

The `ETag` of a masked read is the resource's. A paginated `list` masks each of `items` and keeps
`nextPageToken`. Other actions, and any response that is not `200`, ignore the mask. With
`rn_forge.django.drf.openapi.WireAutoSchema` the schema documents `readMask` on those three
actions. A view outside `BaseModelViewSet` adds `ReadMaskMixin` from `rn_forge.django.drf`;
`read_mask_actions` names the actions it applies to.

## Export, import and batch operations

Tabular export and import, and batch create and delete, are in
`rn_forge.django.drf.transfer` (the `transfer` extra) and are not part of the base classes — see
[Transfer](transfer.md).

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

## Sorting and paging

`OrderByFilter` reads AIP-132 `orderBy` over the view's `ordering_fields`, and
`CursorPagination` pages in that order. `orderBy` is a comma-separated list; a
field may be nullable or span a relation (`author__name`), and rows whose value
is `NULL` come last in both directions. The primary key breaks ties.

```python
from rn_forge.django.drf import CursorPagination, OrderByFilter


class PersonViewSet(BaseModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonSerializer
    pagination_class = CursorPagination
    filter_backends = [OrderByFilter]
    ordering_fields = ["team", "score", "id"]  # score is nullable
```

```http
GET /people?orderBy=team,score%20desc&pageSize=2
```

A page token holds one value per term, so a token issued under another
`orderBy` is a 400.

## Exceptions

Register the normalized JSON exception handler in DRF settings:

```python
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.drf_exception_handler",
}
```

`ExceptionContextViewMixin` (included in the base views) supplies friendlier per-action error
messages (e.g. "Error creating records.") consumed by that handler.
