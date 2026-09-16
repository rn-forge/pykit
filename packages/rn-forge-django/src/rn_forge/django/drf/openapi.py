"""OpenAPI through drf-spectacular, held to the same conventions as the FastAPI stack.

**Requires the ``openapi`` extra.** Not re-exported from any facade; import it
directly.

Three things an application otherwise gets wrong, each shipped as code:

- :data:`SPECTACULAR_SETTINGS` — OpenAPI **3.1.0**, camelCase names, the
  ``ProblemDetail`` component always present, and the camelCase schema hook.
  Spread it into your own ``SPECTACULAR_SETTINGS`` and override what you must.
- :class:`WireAutoSchema` — the ``operationId`` and paginated-component naming
  conventions, read from :mod:`rn_forge.web.openapi` so that this stack and the
  FastAPI one apply one rule rather than two copies of it. A generated client
  gets the same method names and the same page type on either. Name it as
  ``REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]``.
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

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from rn_forge.django.drf.casing import camelize_key
from rn_forge.web.openapi import operation_id, page_component_name

__all__ = [
    "OPENAPI_VERSION",
    "PROBLEM_DETAIL_SCHEMA",
    "SPECTACULAR_SETTINGS",
    "PrincipalBasicAuthenticationScheme",
    "PrincipalBearerAuthenticationScheme",
    "WireAutoSchema",
    "camelize_schema_hook",
]

OPENAPI_VERSION: Final = "3.1.0"
"""The OpenAPI version both stacks emit. 3.0 and 3.1 differ in nullability."""

PROBLEM_DETAIL_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "description": "An RFC 9457 problem. Extension members appear at the top level.",
    "required": ["type", "title", "status", "detail", "instance"],
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "instance": {"type": "string"},
    },
    "additionalProperties": True,
}
"""The ``ProblemDetail`` component, appended whether or not a view names it.

The problem handler builds error bodies by hand, so schema collection never
meets a ``ProblemDetail`` serializer — without this the shared error type is
absent from the document, which is the gap ``rn-forge-fastapi``'s
``install_problem_schema`` closes on its side.
"""

SPECTACULAR_SETTINGS: Final[Mapping[str, Any]] = {
    "OAS_VERSION": OPENAPI_VERSION,
    "CAMELIZE_NAMES": True,
    "APPEND_COMPONENTS": {"schemas": {"ProblemDetail": PROBLEM_DETAIL_SCHEMA}},
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "rn_forge.django.drf.openapi.camelize_schema_hook",
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
    """drf-spectacular's ``AutoSchema``, named by the kit's OpenAPI conventions.

    Both rules come from :mod:`rn_forge.web.openapi`, which the FastAPI binding
    reads too:

    - **``operationId``** — ``<resource><Verb>`` in lowerCamelCase for CRUD, and
      ``<resource><Action>`` for an AIP-136 custom method spelled
      ``/orders/<str:pk>:cancel``. An action spelled as a plain path segment
      gets a mechanical name; give it an explicit
      ``@extend_schema(operation_id=...)``.
    - **The paginated component** — ``PageOrderOut`` rather than
      drf-spectacular's ``PaginatedOrderOutList``, so the two stacks put the same
      type name in a generated client.
    """

    @override
    def get_operation_id(self) -> str:
        return operation_id(self.path, self.method)

    @override
    def get_paginated_name(self, serializer_name: str) -> str:
        return page_component_name(serializer_name)


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
