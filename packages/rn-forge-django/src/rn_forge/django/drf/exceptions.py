"""DRF exception handlers for legacy JSON and RFC 9457 responses.

No error library is adopted: ``drf-standardized-errors`` 0.16.0 (checked 2026-09-23) has no RFC 9457
mode, so its ``application/json`` body lacks ``title``, ``status``, ``instance`` and pointer-based
``errors``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import (
    exception_handler,  # pyright: ignore[reportUnknownVariableType]  # DRF stubs leave its parameters untyped
    set_rollback,
)
from rn_forge.django.drf.utils import RequestUtils
from rn_forge.django.exceptions import (
    json_exception_response,
    problem_details_response,
)
from rn_forge.web import (
    CONTENT_TOO_LARGE,
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemType,
    default_registry,
    field_error,
)

__all__ = [
    "drf_exception_handler",
    "problem_details_exception_handler",
    "problem_registry",
]


def drf_exception_handler(
    exc: Exception, context: Mapping[str, object]
) -> JsonResponse:
    """Handle DRF exceptions with a normalized JSON response."""
    request = cast(Request, context["request"])
    message = cast(str | None, context.get("message", str(exc)))
    status_code = cast(
        int, getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    )
    return json_exception_response(
        RequestUtils.get_django_request(request),
        str(exc),
        message,
        status_code,
    )


def problem_registry(*, type_base: str = "") -> ProblemRegistry:
    """Return the default problem registry with DRF validation mapped to 422.

    Also maps Django's own ``RequestDataTooBig`` (raised when a body exceeds
    ``DATA_UPLOAD_MAX_MEMORY_SIZE``) to 413 — Django's default is 400.

    Args:
        type_base: Forwarded to :func:`rn_forge.web.default_registry`.
    """
    return (
        default_registry(type_base=type_base)
        .register(ValidationError, VALIDATION_ERROR)
        .register(RequestDataTooBig, CONTENT_TOO_LARGE)
    )


_REGISTRY: Final = problem_registry()


def problem_details_exception_handler(
    exc: Exception,
    context: Mapping[str, object],
    *,
    registry: ProblemRegistry | None = None,
) -> JsonResponse:
    """Render an exception as an RFC 9457 ``application/problem+json`` response.

    DRF determines the status and headers first; the registry then supplies the
    problem body. Validation field errors appear in the ``errors`` extension.

    Args:
        exc: The exception DRF caught.
        context: DRF's handler context; ``context["request"]`` gives the path.
        registry: The rows to render with. Defaults to :func:`problem_registry`,
            built once at import.
    """
    rows = registry if registry is not None else _REGISTRY
    drf_response: Response | None = exception_handler(exc, context)
    # DRF only rolls back what it handled; a 500 rendered here must not commit.
    set_rollback()

    request = cast(Request | None, context.get("request"))
    instance = RequestUtils.get_django_request(request).path if request else ""
    row = _problem_type(rows, exc, drf_response)

    detail: str | None = None
    extensions: dict[str, Any] = {}
    if isinstance(exc, RequestDataTooBig):
        detail = "Request body exceeds the configured limit"
    elif isinstance(exc, APIException) and row.status < 500:
        raw = cast(object, exc.detail)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs type detail's nested dicts with unknown keys
        errors = _field_errors(raw)
        if errors:
            extensions["errors"] = errors
            detail = row.title
        else:
            detail = str(raw)

    headers = (
        {k: v for k, v in drf_response.headers.items() if k.lower() != "content-type"}
        if drf_response is not None
        else None
    )
    return problem_details_response(
        exc,
        instance=instance,
        registry=rows,
        problem=row,
        detail=detail,
        extensions=extensions,
        headers=headers,
    )


def _problem_type(
    rows: ProblemRegistry, exc: Exception, drf_response: Response | None
) -> ProblemType:
    """Resolve the row: registered by MRO, else DRF's status, else the fallback."""
    registered = rows.rows()
    if any(cls in registered for cls in type(exc).__mro__):
        return rows.problem_for(exc)
    if drf_response is not None:
        return rows.problem_for_status(drf_response.status_code)
    return rows.problem_for(exc)


def _field_errors(raw: object) -> list[dict[str, str]]:
    """Map a DRF ``detail`` to :func:`rn_forge.web.field_error` entries; empty for a scalar."""
    if isinstance(raw, (Mapping, list, tuple)):
        errors: list[dict[str, str]] = []
        _walk(cast("object", raw), (), errors)
        return errors
    return []


def _walk(node: object, path: tuple[str, ...], out: list[dict[str, str]]) -> None:
    """Depth-first walk of a DRF error tree, one entry per message."""
    if isinstance(node, Mapping):
        for key, value in cast("Mapping[object, object]", node).items():
            _walk(value, (*path, str(key)), out)
    elif isinstance(node, (list, tuple)):
        items = list(cast("Sequence[object]", node))
        # A list of scalars is a field's messages; a list of mappings is a
        # nested serializer, and the index is part of the pointer.
        scalars = all(not isinstance(item, (Mapping, list, tuple)) for item in items)
        for index, item in enumerate(items):
            _walk(item, path if scalars else (*path, str(index)), out)
    else:
        out.append(field_error(path, str(node)))
