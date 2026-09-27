"""Framework-independent OpenAPI operation naming and problem-response declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Final, cast

from rn_forge.web.problem import INTERNAL_ERROR, PROBLEM_MEDIA_TYPE, ProblemRegistry

__all__ = [
    "API_CATALOG_PATH",
    "DOCS_PATH",
    "LINKSET_MEDIA_TYPE",
    "OPENAPI_PATH",
    "PROBLEM_DETAIL_REF",
    "add_problem_responses",
    "api_catalog_body",
    "operation_id",
    "problem_response",
    "problem_statuses",
]

OPENAPI_PATH: Final = "/openapi.json"
"""Default path of the OpenAPI document."""

DOCS_PATH: Final = "/docs"
"""Default path of the human-readable documentation UI."""

API_CATALOG_PATH: Final = "/.well-known/api-catalog"
"""RFC 9727's well-known URI for the API catalog."""

LINKSET_MEDIA_TYPE: Final = "application/linkset+json"
"""The media type of an RFC 9264 linkset, which RFC 9727 requires for the catalog."""

PROBLEM_DETAIL_REF: Final = "#/components/schemas/ProblemDetail"
"""The ``$ref`` every declared problem response points at."""


def api_catalog_body(
    *,
    anchor: str,
    service_desc: str,
    service_doc: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Return the RFC 9727 ``/.well-known/api-catalog`` body.

    An RFC 9264 linkset with one entry, following RFC 9727 §4's example: the
    machine-readable description (RFC 8631's ``service-desc`` relation, in
    practice the OpenAPI document) is required, and the human documentation
    (``service-doc``) and the API's status (``status``, in practice
    readiness) are added when given.

    Args:
        anchor: The API's base URI.
        service_desc: The OpenAPI document's URI.
        service_doc: The human documentation's URI.
        status: The status endpoint's URI.

    Returns:
        ``{"linkset": [{"anchor": ..., "service-desc": [{"href": ...}], ...}]}``.
    """
    entry: dict[str, Any] = {"anchor": anchor, "service-desc": [{"href": service_desc}]}
    if service_doc is not None:
        entry["service-doc"] = [{"href": service_doc}]
    if status is not None:
        entry["status"] = [{"href": status}]
    return {"linkset": [entry]}


def problem_statuses(registry: ProblemRegistry) -> list[int]:
    """Return every status *registry* can render, plus 500, ascending."""
    return sorted(
        {row.status for row in registry.rows().values()} | {INTERNAL_ERROR.status}
    )


def problem_response(status: int) -> dict[str, Any]:
    """Return the OpenAPI response object for a problem with *status*."""
    return {
        "description": HTTPStatus(status).phrase,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": PROBLEM_DETAIL_REF}}},
    }


def add_problem_responses(
    document: Mapping[str, Any], registry: ProblemRegistry
) -> None:
    """Declare a problem response for each of :func:`problem_statuses` on every operation.

    Mutates *document* in place. A response the author already declared for a
    status is never overwritten. The ``ProblemDetail`` component itself is the
    caller's to add.

    Args:
        document: An OpenAPI document, as a generator emitted it.
        registry: The rows the application's problem handler renders with.
    """
    statuses = problem_statuses(registry)
    paths = cast("Mapping[str, Mapping[str, Any]]", document.get("paths", {}))
    for path_item in paths.values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = cast("dict[str, Any]", operation).setdefault("responses", {})
            for status in statuses:
                responses.setdefault(str(status), problem_response(status))


_VERBS: Final[Mapping[str, str]] = {
    "POST": "Create",
    "PUT": "Update",
    "PATCH": "PartialUpdate",
    "DELETE": "Delete",
}

_UNDERSCORE_LETTER: Final = re.compile(r"_([a-zA-Z])")


def _camel(segment: str) -> str:
    """``work-items`` → ``workItems``."""
    return _UNDERSCORE_LETTER.sub(
        lambda match: match.group(1).upper(), segment.replace("-", "_")
    )


def operation_id(path: str, method: str) -> str:
    """Return the ``operationId`` for *path* and *method*: ``<resource><Verb>``.

    The result is lower camel case. For CRUD, *resource* is the last literal
    path segment
    (``/api/v1/work-items/{id}`` → ``workItems``); *Verb* is ``List`` for a
    ``GET`` on a collection and ``Get`` for one on an item (the path ends in a
    parameter), ``Create`` for ``POST``, ``Update`` for ``PUT``,
    ``PartialUpdate`` for ``PATCH``, and ``Delete`` for ``DELETE``.

    Custom methods follow `AIP-136 <https://google.aip.dev/136>`_: an action
    that is not one of the six above is addressed as ``:action`` on the resource
    it acts on, and is named ``<resource><Action>`` regardless of HTTP method.
    ``POST /orders/{orderId}:cancel`` → ``ordersCancel``;
    ``POST /orders:batchCreate`` → ``ordersBatchCreate``.

    Routes that do not encode custom methods with the colon form require an
    explicit framework-specific override.

    Args:
        path: The route's path template, parameters in braces.
        method: The HTTP method, any case.

    Returns:
        The ``operationId``.
    """
    segments = [segment for segment in path.split("/") if segment]
    if segments and ":" in segments[-1]:
        return _custom_method_id(segments)
    literals = [segment for segment in segments if not segment.startswith("{")]
    resource = _camel(literals[-1]) if literals else "root"
    upper = method.upper()
    if upper == "GET":
        verb = "Get" if segments and segments[-1].startswith("{") else "List"
    else:
        verb = _VERBS.get(upper, upper.capitalize())
    return f"{resource}{verb}"


def _custom_method_id(segments: list[str]) -> str:
    """``['orders', '{orderId}:cancel']`` → ``ordersCancel`` (AIP-136)."""
    head, _, action = segments[-1].partition(":")
    literals = [segment for segment in segments[:-1] if not segment.startswith("{")]
    if head and not head.startswith("{"):
        literals.append(head)
    resource = _camel(literals[-1]) if literals else "root"
    verb = _camel(action)
    return f"{resource}{verb[:1].upper()}{verb[1:]}"
