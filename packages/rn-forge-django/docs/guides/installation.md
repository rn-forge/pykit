# Installation

Base package:

```bash
uv add rn-forge-django
```

All optional integrations:

```bash
uv add "rn-forge-django[all]"
```

Targeted extras:

| Extra | Adds |
| --- | --- |
| `drf` | Django REST Framework integration (views, serializers, exceptions), including Excel transfer support via `rn-forge-commons[excel]` |
| `jwt` | `drf` + `djangorestframework-simplejwt`-backed JWT auth |
| `saml` | `drf` + `djangorestframework-simplejwt` + `python3-saml` SAML auth support |
| `fixtures` | `rn-forge-commons[excel]`, for building Django JSON fixtures from Excel workbooks |
| `all` | Everything above |

To use the bundled auth app, add `"rn_forge.django.auth"` to `INSTALLED_APPS`.

Docs commands:

```bash
uv run --directory packages/rn-forge-django --group docs mkdocs serve
uv run --directory packages/rn-forge-django --group docs mkdocs build
```
