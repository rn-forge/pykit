"""Framework-independent OpenAPI operation and component naming."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

__all__ = ["operation_id", "page_component_name"]

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


def page_component_name(item: str) -> str:
    """Return the component name for a page of *item*: ``Page<Item>``.

    ``page_component_name("OrderOut")`` → ``"PageOrderOut"``.

    OpenAPI has no generic components, so each concrete page includes its item
    component name.

    Args:
        item: The item component's name, as it appears in ``components/schemas``.

    Returns:
        The page component's name.
    """
    return f"Page{item}"
