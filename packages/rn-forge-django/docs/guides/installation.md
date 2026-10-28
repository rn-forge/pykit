# Installation

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-django>=0.6,<0.7"]
```

Extras go in brackets after the name:

```toml
dependencies = ["rn-forge-django[drf]>=0.6,<0.7"]
```

or, from the command line:

```bash
uv add "rn-forge-django[all]>=0.6,<0.7"
```

Base dependencies are Django, `rn-forge-commons` and `rn-forge-web`, each
required by version range.

| Extra | Adds |
| -- | -- |
| `drf` | Django REST Framework integration (views, serializers, exceptions, pagination, idempotency, concurrency, casing) |
| `transfer` | `django-import-export` + `rn-forge-data` (`tablib`, `openpyxl`), for `rn_forge.django.drf.transfer`: tabular export and import, batch create and delete |
| `openapi` | `djangorestframework` + `drf-spectacular`, for `rn_forge.django.drf.openapi` |
| `oidc` | `djangorestframework` + `rn-forge-auth[oidc]` (`pyjwt[crypto]`), for `rn_forge.django.auth.drf.oidc` |
| `redis` | `rn-forge-auth[redis]`, the client for Django's Redis cache backend that holds login transactions and revoked session IDs |
| `celery` | `celery`, for `rn_forge.django.celery` |
| `fixtures` | `rn-forge-data[pandas]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

There is deliberately no `messaging` extra —
`rn_forge.django.messaging` is Django ORM plus stdlib.

To use the bundled auth app, add `"rn_forge.django.auth"` to `INSTALLED_APPS`.
For the OpenAPI integration, add `"drf_spectacular"`.

Docs commands:

```bash
uv run --directory packages/rn-forge-django --group docs mkdocs serve
uv run --directory packages/rn-forge-django --group docs mkdocs build
```
