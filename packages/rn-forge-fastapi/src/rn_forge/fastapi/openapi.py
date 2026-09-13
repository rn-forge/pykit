"""OpenAPI repair: put the error type back in the schema, and name operations once.

**The non-obvious module.** FastAPI builds ``components/schemas`` from the
``response_model``\\ s routes declare. The problem handlers build error bodies by
hand, so schema collection never sees ``ProblemDetail`` — and a TypeScript
client generated from the schema ends up with no error type at all. Worse,
every route with a parameter advertises FastAPI's own 422 shape
(``HTTPValidationError``), which the handlers have replaced.

Three conventions from ``api-conventions.md`` §9, implemented here:

- **OpenAPI 3.1.0**, pinned by :func:`install_problem_schema` rather than
  inherited from whatever the installed FastAPI emits.
- **Identical component names** — ``ProblemDetail``, ``CheckResult``,
  ``HealthReport`` — which is why the mirrors in :mod:`rn_forge.fastapi.schemas`
  are named for the wire.
- **One ``operationId`` convention**, :func:`operation_id`: a generator turns
  ``operationId`` into the client's method name, so two stacks that differ here
  differ at every call site even when every byte of JSON agrees.

This is the one module expected to exceed forty lines: it works around schema
collection rather than adapting a primitive, and that workaround stays here
rather than in the handlers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Final

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic.alias_generators import to_camel

from rn_forge.fastapi.schemas import ProblemDetail
from rn_forge.web import (
    INTERNAL_ERROR,
    PROBLEM_MEDIA_TYPE,
    VALIDATION_ERROR,
    ProblemRegistry,
    default_registry,
)

__all__ = ["OPENAPI_VERSION", "install_problem_schema", "operation_id"]

OPENAPI_VERSION: Final = "3.1.0"
"""The OpenAPI version both stacks emit. 3.0 and 3.1 differ in nullability."""

_PROBLEM_REF: Final = "#/components/schemas/ProblemDetail"
_FASTAPI_VALIDATION_SCHEMAS: Final = ("HTTPValidationError", "ValidationError")
_VERBS: Final[Mapping[str, str]] = {
    "POST": "Create",
    "PUT": "Update",
    "PATCH": "PartialUpdate",
    "DELETE": "Delete",
}


def operation_id(route: APIRoute) -> str:
    """Return the ``operationId`` for *route*: ``<resource><Verb>`` in lowerCamelCase.

    Pass it as ``FastAPI(generate_unique_id_function=operation_id)``.

    - **resource** is the last literal path segment, camelCased:
      ``/api/v1/work-items/{id}`` → ``workItems``.
    - **Verb** is ``List`` for a ``GET`` on a collection and ``Get`` for one on
      an item (the path ends in a parameter); ``Create`` for ``POST``,
      ``Update`` for ``PUT``, ``PartialUpdate`` for ``PATCH`` (distinct, so a
      resource serving both gets two operation IDs), ``Delete`` for ``DELETE``.

    The convention covers CRUD and nothing else. A route outside it — an action
    such as ``POST /orders/{id}/cancel`` — gets a mechanical name
    (``cancelCreate``); give it an explicit ``operation_id=``, which FastAPI
    uses in preference to this function.
    """
    segments = [segment for segment in route.path_format.split("/") if segment]
    literals = [segment for segment in segments if not segment.startswith("{")]
    resource = to_camel(literals[-1].replace("-", "_")) if literals else "root"
    method = min(route.methods) if route.methods else "GET"
    if method == "GET":
        verb = "Get" if segments and segments[-1].startswith("{") else "List"
    else:
        verb = _VERBS.get(method, method.capitalize())
    return f"{resource}{verb}"


def install_problem_schema(
    app: FastAPI,
    *,
    registry: ProblemRegistry | None = None,
    default_responses: bool = True,
) -> None:
    """Put ``ProblemDetail`` into *app*'s OpenAPI document, and pin 3.1.0.

    Idempotent, and it survives FastAPI's schema caching: the repair runs once,
    on the first ``app.openapi()`` call, and the cached document is returned
    thereafter.

    Args:
        app: The application.
        registry: The registry the problem handlers render with. Its statuses,
            plus 500, are the problem responses declared on every operation.
            Defaults to :func:`rn_forge.web.default_registry`.
        default_responses: When ``True``, every operation gains an
            ``application/problem+json`` response for each of those statuses
            it does not already declare, so a generated client knows a 409 or a
            412 is possible. An author's own ``responses=`` entry is never
            overwritten. FastAPI's generated 422 is always replaced, because the
            handlers have replaced the body it describes.
    """
    rows = (registry if registry is not None else default_registry()).rows()
    statuses = sorted({row.status for row in rows.values()} | {INTERNAL_ERROR.status})
    app.openapi_version = OPENAPI_VERSION
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build()
        _repair(schema, statuses if default_responses else [])
        app.openapi_schema = schema
        return schema

    app.openapi = openapi


def _repair(schema: dict[str, Any], statuses: list[int]) -> None:
    """Inject the ``ProblemDetail`` component and the problem responses."""
    components: dict[str, Any] = schema.setdefault("components", {}).setdefault(
        "schemas", {}
    )
    components.setdefault(
        "ProblemDetail", ProblemDetail.model_json_schema(mode="serialization")
    )
    paths: dict[str, dict[str, Any]] = schema.get("paths", {})
    for path_item in paths.values():
        for operation in path_item.values():
            responses: dict[str, Any] = operation.setdefault("responses", {})
            status = str(VALIDATION_ERROR.status)
            if _is_fastapi_validation_response(responses.get(status)):
                responses[status] = _problem_response(VALIDATION_ERROR.status)
            for code in statuses:
                responses.setdefault(str(code), _problem_response(code))
    if not any(
        f"#/components/schemas/{name}" in json.dumps(paths)
        for name in _FASTAPI_VALIDATION_SCHEMAS
    ):
        for name in _FASTAPI_VALIDATION_SCHEMAS:
            components.pop(name, None)


def _problem_response(status: int) -> dict[str, Any]:
    return {
        "description": HTTPStatus(status).phrase,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": _PROBLEM_REF}}},
    }


def _is_fastapi_validation_response(response: Any) -> bool:
    return isinstance(
        response, dict
    ) and '"#/components/schemas/HTTPValidationError"' in json.dumps(response)
