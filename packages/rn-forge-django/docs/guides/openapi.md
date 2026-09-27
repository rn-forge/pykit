# OpenAPI and camelCase

An `rn-forge-django` API and an `rn-forge-fastapi` API describe themselves the same way: OpenAPI
**3.1.0**, camelCase property names, the shared `ProblemDetail`, `CheckResult` and `HealthReport`
components, and `operationId`s of the form `<resource><Verb>`. The wire conventions themselves are
specified by `rn-forge-web`'s `api-conventions.md`; this page is only the Django wiring.

Install the `openapi` extra (see [Installation](installation.md)) and add `drf_spectacular` to
`INSTALLED_APPS`. Then:

```python
from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS as RNF_SPECTACULAR

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rn_forge.django.drf.pagination.CursorPagination",
    "DEFAULT_SCHEMA_CLASS": "rn_forge.django.drf.openapi.WireAutoSchema",
}

SPECTACULAR_SETTINGS = {**RNF_SPECTACULAR, "TITLE": "Orders API", "VERSION": "1.0.0"}
```

That is the whole of it. What each piece does:

| Setting | Effect |
| --- | --- |
| `CamelCaseJSONRenderer` / `CamelCaseJSONParser` | camelCase out; camelCase **or** `snake_case` in. Switch off with `RN_FORGE_DJANGO["DRF"]["CASING"]["ENABLED"] = False` |
| `WireAutoSchema` | `operationId` = `<resource><Verb>` (`workItemsList`, `workItemsGet`, `workItemsCreate`, ...), `<resource><Action>` for an AIP-136 custom method (`/orders/<str:pk>:cancel` → `ordersCancel`). Read from `rn_forge.web.openapi`, which the FastAPI binding reads too. The paginated component keeps drf-spectacular's own name (`Paginated<Item>List`) — document text is not held identical across stacks |
| `SPECTACULAR_SETTINGS` | pins OAS 3.1.0, always emits `ProblemDetail`, camelizes component property names, and declares an `application/problem+json` response for every status the problem handler can render, on every operation |
| importing `rn_forge.django.drf.openapi` | registers `bearerAuth` / `basicAuth` security schemes for the principal authentication classes |

## Serving the document, the docs UI, and the API catalog

```python
from rn_forge.django.drf.openapi import openapi_urlpatterns

urlpatterns = [
    *openapi_urlpatterns(),
    # ... your own routes
]
```

Mounts drf-spectacular's `SpectacularAPIView` at `/openapi.json`,
`SpectacularSwaggerView` at `/docs`, and RFC 9727's
`/.well-known/api-catalog` — an RFC 9264 linkset naming both, plus
`/readyz`. Pass `readiness_path=` if yours differs.

## Opaque JSON values

Global casing rewrites every nested key. A field whose value is data keyed by something other than
a Python name — a vendor payload, a mapping keyed by SKU — must be declared as
`RawPassthroughField`, which keeps its keys verbatim in both directions:

```python
from rn_forge.django.drf.serializers import RawPassthroughField

class OrderSerializer(serializers.Serializer):
    vendor_payload = RawPassthroughField()
```

## The shared components

`ProblemDetail` and `HealthReport` (and its `CheckResult`) are the `rn_forge.web` pydantic models.
Name one in `@extend_schema(responses=...)` and drf-spectacular's pydantic extension emits the
component under its shared name, camelCase properties included. The `ProblemDetail` component is
always present. A page is described by the paginator's own `get_paginated_response_schema`, not by
`Page`.
