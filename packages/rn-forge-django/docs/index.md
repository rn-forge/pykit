# rn-forge-django

`rn-forge-django` is the opinionated Django/DRF integration layer built on top
of `rn-forge-commons`.

It provides:

- abstract model base classes: status/audit fields, natural-key fixture support,
  opt-in validation-on-save
- a typed, auto-reloading settings facade for the `RN_FORGE_DJANGO` Django
  setting
- an installable auth app: the `/auth` routes over `rn-forge-auth`, sessions,
  and DRF authentication and permission classes
- DRF base views and mixins: tabular export/import and batch create/delete
  (`transfer` extra), audit-field population, auth-aware permissions
- Excel-to-fixture generation for Django `loaddata`

## Install

```toml
dependencies = ["rn-forge-django>=0.6,<0.7"]
```

Extras: `drf`, `transfer`, `openapi`, `oidc`, `redis`, `celery`, `fixtures`,
`security`, `cors`, `otel` and `all`; see
[Installation](guides/installation.md). Minimum example:
[Quickstart](guides/quickstart.md). Set
`rn_forge.django.drf.exceptions.problem_details_exception_handler` as the DRF
exception handler to render every error as RFC 9457 `application/problem+json`;
see [DRF Views](guides/drf-views.md#exceptions).

Use the guides for common workflows and the API reference for module details.
