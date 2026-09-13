"""DRF-specific exception helpers.

Two handlers, and a consumer picks one through its own
``REST_FRAMEWORK["EXCEPTION_HANDLER"]``; this package wires neither:

- :func:`drf_exception_handler` — this package's original
  ``{"path", "error", "message"}`` body.
- :func:`problem_details_exception_handler` — RFC 9457
  ``application/problem+json``, the wire contract shared with
  ``rn-forge-fastapi`` and specified in ``rn-forge-web``'s
  ``api-conventions.md``. Choose this one for any new API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

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
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemType,
    default_registry,
    errors_from_field_map,
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
    """Return a fresh :func:`rn_forge.web.default_registry` with DRF's one extra row.

    DRF's ``ValidationError`` is registered against ``validation-error``/422 —
    the status the shared contract gives a validation failure, where DRF alone
    would say 400. Every other DRF ``APIException`` needs no row: it resolves
    by the status DRF gives it, through
    :meth:`rn_forge.web.ProblemRegistry.problem_for_status`.

    Args:
        type_base: Forwarded to :func:`rn_forge.web.default_registry`.
    """
    return default_registry(type_base=type_base).register(
        ValidationError, VALIDATION_ERROR
    )


_REGISTRY: Final = problem_registry()


def problem_details_exception_handler(
    exc: Exception,
    context: Mapping[str, object],
    *,
    registry: ProblemRegistry | None = None,
) -> JsonResponse:
    """Render an exception as an RFC 9457 ``application/problem+json`` response.

    DRF's default ``exception_handler`` runs first, so DRF keeps doing what it
    does well — turning ``Http404`` into a 404, attaching the authenticator's
    ``WWW-Authenticate`` challenge and a throttle's ``Retry-After``, rolling
    back an atomic request. Its status and headers are then re-clothed as a
    problem; its ``{"detail": ...}`` body is discarded.

    - An exception with a row on the registry (by MRO) renders from that row.
    - Any other DRF ``APIException`` renders from the row for the status DRF
      gave it.
    - Anything else is the registry's fallback: a 500 whose detail says nothing.

    Field errors are normalized with :func:`rn_forge.web.errors_from_field_map`
    into the ``errors`` extension, present only when non-empty.

    Use it as ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``. To register an
    application's own exceptions, or set a ``type`` URI base, wrap it with a
    :func:`problem_registry` of your own passed as *registry*.

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
    if isinstance(exc, APIException) and row.status < 500:
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
    """Normalize a DRF ``detail`` into pointer/message pairs; empty for a scalar."""
    if isinstance(raw, Mapping):
        return errors_from_field_map(cast(Mapping[str, Any], raw))
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return [
            {"pointer": "", "message": str(item)}
            for item in cast(Sequence[object], raw)
        ]
    return []
