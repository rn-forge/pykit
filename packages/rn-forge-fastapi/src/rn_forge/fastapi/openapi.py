"""Repair FastAPI OpenAPI documents to match the shared wire contract.

Accuracy only: the repair adds the ``ProblemDetail`` component and declares
the problem+json responses the app can actually produce, and removes
FastAPI's replaced validation schema. It does not rename components or pin an
OpenAPI version.
"""

from __future__ import annotations

import json
from typing import Any, Final

from fastapi.routing import APIRoute
from rn_forge.web import ProblemDetail
from rn_forge.web import VALIDATION_ERROR, ProblemRegistry, default_registry
from rn_forge.web.openapi import (
    add_problem_responses,
    problem_response,
)
from rn_forge.web.openapi import operation_id as wire_operation_id

__all__ = ["operation_id"]

_SCHEMA_REF_PREFIX: Final = "#/components/schemas/"
_FASTAPI_VALIDATION_SCHEMAS: Final = ("HTTPValidationError", "ValidationError")


def operation_id(route: APIRoute) -> str:
    """Return the ``operationId`` for *route*, per :func:`rn_forge.web.operation_id`.

    Pass it as ``FastAPI(generate_unique_id_function=operation_id)``. Use an
    explicit ``operation_id=`` for routes that cannot follow the shared rule.
    """
    method = min(route.methods) if route.methods else "GET"
    return wire_operation_id(route.path_format, method)


def repair_problem_schema(
    schema: dict[str, Any], *, registry: ProblemRegistry | None = None
) -> dict[str, Any]:
    """Repair *schema* in place: declare the problem responses, and nothing else.

    Called once by :meth:`rn_forge.fastapi.app.FastApiApp.openapi` against the
    document it caches, so the repair never re-runs. It keeps the
    ``ProblemDetail`` component, adds an ``application/problem+json`` response
    for each of *registry*'s statuses (plus 500) to every operation that does
    not already declare one, and replaces FastAPI's own 422 — the validation
    handlers have replaced the body it describes.

    Args:
        schema: The document FastAPI built, as returned by its own
            ``openapi()``.
        registry: The rows the app's problem handlers render with. Defaults to
            :func:`rn_forge.web.default_registry`.

    Returns:
        *schema*, for chaining.
    """
    rows = registry if registry is not None else default_registry()
    components: dict[str, Any] = schema.setdefault("components", {}).setdefault(
        "schemas", {}
    )
    components.setdefault(
        "ProblemDetail", ProblemDetail.model_json_schema(mode="serialization")
    )
    paths: dict[str, dict[str, Any]] = schema.get("paths", {})
    status = str(VALIDATION_ERROR.status)
    for path_item in paths.values():
        for operation in path_item.values():
            responses: dict[str, Any] = operation.setdefault("responses", {})
            if _is_fastapi_validation_response(responses.get(status)):
                responses[status] = problem_response(VALIDATION_ERROR.status)
    add_problem_responses(schema, rows)
    if not any(
        f"{_SCHEMA_REF_PREFIX}{name}" in json.dumps(paths)
        for name in _FASTAPI_VALIDATION_SCHEMAS
    ):
        for name in _FASTAPI_VALIDATION_SCHEMAS:
            components.pop(name, None)
    return schema


def _is_fastapi_validation_response(response: Any) -> bool:
    return isinstance(
        response, dict
    ) and '"#/components/schemas/HTTPValidationError"' in json.dumps(response)
