"""Repair FastAPI OpenAPI documents to match the shared wire contract.

The repair adds problem schemas and responses, removes FastAPI's replaced
validation schema, normalizes generic component names, and pins OpenAPI 3.1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Final, cast

from fastapi import FastAPI
from fastapi.routing import APIRoute

from rn_forge.fastapi.schemas import ProblemDetail
from rn_forge.web import (
    INTERNAL_ERROR,
    PROBLEM_MEDIA_TYPE,
    VALIDATION_ERROR,
    ProblemRegistry,
    default_registry,
)
from rn_forge.web.openapi import operation_id as wire_operation_id

__all__ = ["OPENAPI_VERSION", "install_problem_schema", "operation_id"]

OPENAPI_VERSION: Final = "3.1.0"
"""The OpenAPI version both stacks emit. 3.0 and 3.1 differ in nullability."""

_SCHEMA_REF_PREFIX: Final = "#/components/schemas/"
_PROBLEM_REF: Final = f"{_SCHEMA_REF_PREFIX}ProblemDetail"
_FASTAPI_VALIDATION_SCHEMAS: Final = ("HTTPValidationError", "ValidationError")


def operation_id(route: APIRoute) -> str:
    """Return the ``operationId`` for *route*, per :func:`rn_forge.web.operation_id`.

    Pass it as ``FastAPI(generate_unique_id_function=operation_id)``. Use an
    explicit ``operation_id=`` for routes that cannot follow the shared rule.
    """
    method = min(route.methods) if route.methods else "GET"
    return wire_operation_id(route.path_format, method)


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
    """Rename generic components, inject ``ProblemDetail``, add the responses."""
    _rename_generic_components(schema)
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


def _rename_generic_components(schema: dict[str, Any]) -> None:
    """``Page_OrderOut_`` → ``PageOrderOut``, references included.

    Colliding component names are left unchanged.
    """
    components: dict[str, Any] = schema.get("components", {}).get("schemas", {})
    renames: dict[str, str] = {}
    for name in components:
        if not name.endswith("_"):
            continue
        flattened = "".join(
            part[:1].upper() + part[1:] for part in name.split("_") if part
        )
        if flattened != name and flattened not in components:
            renames[name] = flattened
    if not renames:
        return
    for old_name, new_name in renames.items():
        components[new_name] = components.pop(old_name)
    _rewrite_refs(schema, renames)


def _rewrite_refs(node: Any, renames: Mapping[str, str]) -> None:
    """Repoint every ``$ref`` in *node* that names a renamed component."""
    if isinstance(node, dict):
        for key, value in cast(dict[str, Any], node).items():
            if key == "$ref" and isinstance(value, str):
                name = value.removeprefix(_SCHEMA_REF_PREFIX)
                if name != value and name in renames:
                    node[key] = f"{_SCHEMA_REF_PREFIX}{renames[name]}"
            else:
                _rewrite_refs(value, renames)
    elif isinstance(node, list):
        for item in cast(list[Any], node):
            _rewrite_refs(item, renames)


def _problem_response(status: int) -> dict[str, Any]:
    return {
        "description": HTTPStatus(status).phrase,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": _PROBLEM_REF}}},
    }


def _is_fastapi_validation_response(response: Any) -> bool:
    return isinstance(
        response, dict
    ) and '"#/components/schemas/HTTPValidationError"' in json.dumps(response)
