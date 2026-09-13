# Installation

`rn-forge-django` is not on PyPI. A release is a git tag (`rn-forge-django-v<version>`), and a
consumer declares a pinned direct URL to it:

```toml
[project]
dependencies = [
  "rn-forge-django @ git+https://github.com/rn-forge/pykit@rn-forge-django-v0.3.0#subdirectory=packages/rn-forge-django",
]
```

Extras use the same form, with the extra before the `@`:

```toml
dependencies = [
  "rn-forge-django[drf] @ git+https://github.com/rn-forge/pykit@rn-forge-django-v0.3.0#subdirectory=packages/rn-forge-django",
]
```

or, from the command line:

```bash
uv add "rn-forge-django[all] @ git+https://github.com/rn-forge/pykit@rn-forge-django-v0.3.0#subdirectory=packages/rn-forge-django"
```

Base dependencies are Django, `rn-forge-commons` and `rn-forge-web`, each pinned to its own release
tag.

| Extra | Adds |
| --- | --- |
| `drf` | Django REST Framework integration (views, serializers, exceptions, pagination, idempotency, concurrency, casing), including Excel transfer support via `rn-forge-commons[excel]` |
| `jwt` | `djangorestframework` + `djangorestframework-simplejwt`-backed JWT auth — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `saml` | `djangorestframework` + `djangorestframework-simplejwt` + `python3-saml` SAML auth support — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `openapi` | `djangorestframework` + `drf-spectacular`, for `rn_forge.django.drf.openapi` — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `oidc` | `djangorestframework` + `rn-forge-commons[auth]` (`pyjwt[crypto]`), for `rn_forge.django.auth.drf.oidc` — plus `rn-forge-commons[excel]`, which every DRF-bringing extra needs because the `drf` facade loads the Excel transfer views |
| `celery` | `celery`, for `rn_forge.django.celery` |
| `fixtures` | `rn-forge-commons[excel]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

`oidc` is its own extra rather than part of `jwt`: verifying externally issued tokens against a
JWKS endpoint has nothing to do with simplejwt, and should not install it. There is deliberately no
`messaging` extra — `rn_forge.django.messaging` is Django ORM plus stdlib.

To use the bundled auth app, add `"rn_forge.django.auth"` to `INSTALLED_APPS`. For the OpenAPI
integration, add `"drf_spectacular"`.

Docs commands:

```bash
uv run --directory packages/rn-forge-django --group docs mkdocs serve
uv run --directory packages/rn-forge-django --group docs mkdocs build
```
