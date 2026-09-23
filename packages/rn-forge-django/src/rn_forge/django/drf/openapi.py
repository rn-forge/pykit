"""OpenAPI through drf-spectacular, held to the same conventions as the FastAPI stack.

**Requires the ``openapi`` extra.** Not re-exported from any facade; import it
directly.

Four things an application otherwise gets wrong, each shipped as code:

- :data:`SPECTACULAR_SETTINGS` — OpenAPI **3.1.0**, camelCase names, the
  ``ProblemDetail`` component always present, and the camelCase and
  problem-response schema hooks. Spread it into your own
  ``SPECTACULAR_SETTINGS`` and override what you must.
- :class:`WireAutoSchema` — the ``operationId`` convention, read from
  :mod:`rn_forge.web.openapi` so that this stack and the FastAPI one apply one
  rule rather than two copies of it. A generated client gets the same method
  names on either — document text otherwise is not held identical across
  stacks; drf-spectacular's own paginated-component name is kept. Name it as
  ``REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]``.
- :func:`problem_responses_hook` — declares an ``application/problem+json``
  response, referencing ``ProblemDetail``, for every status the problem
  handler can render, on every operation that does not already declare one.
  The FastAPI binding's ``FastApiApp.openapi()`` closes the identical gap on
  its side.
- The security-scheme extensions for
  :class:`~rn_forge.django.auth.drf.principal.PrincipalBearerAuthentication` and
  its Basic twin. drf-spectacular discovers extensions by import, so importing
  this module — which naming :class:`WireAutoSchema` in settings does — registers
  them.

The ``djangorestframework_camel_case`` postprocessing hook drf-spectacular
documents is not used; :func:`camelize_schema_hook` is its replacement, for the
reason given in :mod:`rn_forge.django.drf.casing`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast, override

from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, path
from django.views.decorators.http import require_http_methods
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rn_forge.django.drf.casing import camelize_key
from rn_forge.django.drf.exceptions import problem_registry
from rn_forge.web import (
    ProblemDetail,
    API_CATALOG_PATH,
    DOCS_PATH,
    LINKSET_MEDIA_TYPE,
    OPENAPI_PATH,
    READINESS_PATH,
    api_catalog_body,
)
from rn_forge.web.openapi import (
    add_problem_responses,
    operation_id,
)

__all__ = [
    "OPENAPI_VERSION",
    "SPECTACULAR_SETTINGS",
    "PrincipalBasicAuthenticationScheme",
    "PrincipalBearerAuthenticationScheme",
    "WireAutoSchema",
    "camelize_schema_hook",
    "openapi_urlpatterns",
    "problem_responses_hook",
]

OPENAPI_VERSION: Final = "3.1.0"
"""The OpenAPI version both stacks emit. 3.0 and 3.1 differ in nullability."""

SPECTACULAR_SETTINGS: Final[Mapping[str, Any]] = {
    "OAS_VERSION": OPENAPI_VERSION,
    "CAMELIZE_NAMES": True,
    "APPEND_COMPONENTS": {
        "schemas": {
            "ProblemDetail": ProblemDetail.model_json_schema(mode="serialization")
        }
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "rn_forge.django.drf.openapi.camelize_schema_hook",
        "rn_forge.django.drf.openapi.problem_responses_hook",
    ],
}
"""drf-spectacular settings every ``rn-forge-django`` API starts from.

Usage::

    from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS as RNF_SPECTACULAR

    SPECTACULAR_SETTINGS = {**RNF_SPECTACULAR, "TITLE": "Orders API"}
"""


def camelize_schema_hook(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Camelize property names and ``required`` lists in every component schema.

    The document then describes what the camelCase renderer actually emits.
    """
    del generator, request, public
    schemas: dict[str, Any] = result.get("components", {}).get("schemas", {})
    for schema in schemas.values():
        _camelize_schema(cast(dict[str, Any], schema))
    return result


def problem_responses_hook(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Add an ``application/problem+json`` response, by status, to every operation.

    Accuracy only, mirroring ``FastApiApp.openapi()``'s repair on the FastAPI
    side: an author's own ``responses=`` entry for that status is never
    overwritten.
    """
    del generator, request, public
    add_problem_responses(result, problem_registry())
    return result


def _camelize_schema(schema: dict[str, Any]) -> None:
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        camelized: dict[str, Any] = {
            camelize_key(str(name)): value
            for name, value in cast(Mapping[str, Any], properties).items()
        }
        schema["properties"] = camelized
        for value in camelized.values():
            if isinstance(value, dict):
                _camelize_schema(cast(dict[str, Any], value))
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [
            camelize_key(str(name)) for name in cast(list[Any], required)
        ]
    items = schema.get("items")
    if isinstance(items, dict):
        _camelize_schema(cast(dict[str, Any], items))


class WireAutoSchema(AutoSchema):
    """drf-spectacular's ``AutoSchema``, named by the kit's ``operationId`` convention.

    Read from :mod:`rn_forge.web.openapi`, which the FastAPI binding reads too:
    ``<resource><Verb>`` in lowerCamelCase for CRUD, and ``<resource><Action>``
    for an AIP-136 custom method spelled ``/orders/<str:pk>:cancel``. An action
    spelled as a plain path segment gets a mechanical name; give it an explicit
    ``@extend_schema(operation_id=...)``.

    The paginated component keeps drf-spectacular's own name
    (``PaginatedOrderOutList``) — document text is not held identical across
    stacks; only wire behaviour and ``operationId`` are.
    """

    @override
    def get_operation_id(self) -> str:
        return operation_id(self.path, self.method)


class PrincipalBearerAuthenticationScheme(OpenApiAuthenticationExtension):
    """Declares ``PrincipalBearerAuthentication`` as an HTTP bearer security scheme."""

    target_class = "rn_forge.django.auth.drf.principal.PrincipalBearerAuthentication"
    match_subclasses = True
    name = "bearerAuth"

    @override
    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {"type": "http", "scheme": "bearer"}


class PrincipalBasicAuthenticationScheme(OpenApiAuthenticationExtension):
    """Declares ``PrincipalBasicAuthentication`` as an HTTP basic security scheme."""

    target_class = "rn_forge.django.auth.drf.principal.PrincipalBasicAuthentication"
    match_subclasses = True
    name = "basicAuth"

    @override
    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {"type": "http", "scheme": "basic"}


def openapi_urlpatterns(*, readiness_path: str = READINESS_PATH) -> list[URLPattern]:
    """Return URL patterns serving the OpenAPI document, the docs UI, and the API catalog.

    Mounts drf-spectacular's :class:`~drf_spectacular.views.SpectacularAPIView`
    at :data:`~rn_forge.web.OPENAPI_PATH` (JSON) and
    :class:`~drf_spectacular.views.SpectacularSwaggerView` at
    :data:`~rn_forge.web.DOCS_PATH`, plus RFC 9727's
    :data:`~rn_forge.web.API_CATALOG_PATH`, which points at both and at
    *readiness_path*.

    Args:
        readiness_path: The path the catalog's ``status`` relation points at.
    """

    @require_http_methods(["GET", "HEAD"])
    def api_catalog(request: HttpRequest) -> JsonResponse:
        del request
        return JsonResponse(
            api_catalog_body(
                anchor="/",
                service_desc=OPENAPI_PATH,
                service_doc=DOCS_PATH,
                status=readiness_path,
            ),
            content_type=LINKSET_MEDIA_TYPE,
        )

    return [
        path(
            OPENAPI_PATH.lstrip("/"),
            SpectacularAPIView.as_view(),
            name="rn-forge-openapi",
        ),
        path(
            DOCS_PATH.lstrip("/"),
            SpectacularSwaggerView.as_view(url_name="rn-forge-openapi"),
            name="rn-forge-docs",
        ),
        path(
            API_CATALOG_PATH.lstrip("/"),
            api_catalog,
            name="rn-forge-api-catalog",
        ),
    ]
