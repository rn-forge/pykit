# Settings

All configuration lives in a single `RN_FORGE_DJANGO` dict in your Django settings module:

```python
RN_FORGE_DJANGO = {
    "AUTH": {
        "SAML": {
            "SETTINGS": {...},  # python3-saml settings dict
            "RETURN_TO": "/",
        },
    },
    "DRF": {
        "VIEWS": {
            "DEFAULT_TRANSFER_FORMAT": "xlsx",
            "EXPORT_MAX_ROWS": 10_000,
            "IMPORT_MAX_ROWS": 10_000,
            "PERMISSION_ACTION_MAP": {"list": "read"},
        },
        "PAGINATION": {
            "PAGE_SIZE": 50,  # default page size
            "PAGE_SIZE_QUERY_PARAM": "pageSize",
            "MAX_PAGE_SIZE": 200,  # larger requests are clamped, never rejected
        },
        "CASING": {
            "ENABLED": True,  # camelCase renderer/parser; False = plain JSON
        },
    },
}
```

`DRF.PAGINATION` is read at request time by `CursorPagination` and `LegacyPageNumberPagination`;
a `page_size` or `max_page_size` set on a pagination subclass wins over it. `DRF.CASING` switches
`CamelCaseJSONRenderer` and `CamelCaseJSONParser` — see [OpenAPI and camelCase](openapi.md).

Read the resolved, typed settings at runtime via the module-level facade:

```python
from rn_forge.django.settings import rn_forge_django_settings

max_rows = rn_forge_django_settings.drf.views.export_max_rows
saml_settings = rn_forge_django_settings.auth.saml.settings
```

`rn_forge_django_settings` is a frozen dataclass tree rebuilt automatically whenever Django's
`setting_changed` signal fires for `RN_FORGE_DJANGO` — this is what makes
`override_settings(RN_FORGE_DJANGO=...)` work transparently in tests. Every field has a
default, so an empty or missing `RN_FORGE_DJANGO` dict is valid.

## Adding a configurable option

The facade is a frozen dataclass tree — `RnforgeDjangoSettings` → `AuthSettings`/`DRFSettings` →
nested settings — built once by `_build_settings()` in
[`settings.py`](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-django/src/rn_forge/django/settings.py)
and rebuilt by the `setting_changed` handler. A new option needs three edits, in this order:

1. A field on the relevant `*SettingsDict` `TypedDict`, naming the `RN_FORGE_DJANGO` key
   (uppercase, as the dict is written).
2. A field on the matching frozen dataclass, snake_cased, with a default — every field has one,
   so an absent `RN_FORGE_DJANGO` stays valid.
3. Extraction in `_build_settings()`, using `DictUtils.get`/`_get_mapping` for the nested path
   (`"DRF.VIEWS"`, say).

Skipping step 3 leaves the field permanently at its default, which no test catches unless it
asserts the non-default value.
