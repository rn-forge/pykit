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
| `WireAutoSchema` | `operationId` = `<resource><Verb>` (`workItemsList`, `workItemsGet`, `workItemsCreate`, ...) |
| `SPECTACULAR_SETTINGS` | pins OAS 3.1.0, always emits `ProblemDetail`, camelizes component property names |
| importing `rn_forge.django.drf.openapi` | registers `bearerAuth` / `basicAuth` security schemes for the principal authentication classes |

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

`ProblemDetailSerializer`, `PageSerializer`, `CheckResultSerializer` and `HealthReportSerializer`
(in `rn_forge.django.drf.serializers`) are the DRF mirrors of the `rn_forge.web` wire shapes. Name
them in `@extend_schema(responses=...)` so the component appears under its shared name.

## Why there is no camelCase dependency

`djangorestframework-camel-case` was evaluated and not taken: its last release is 1.4.2 (February
2023), its classifiers stop at Python 3.10 and it is marked pre-alpha. The renderer, parser and
schema hook in this package replace it.
