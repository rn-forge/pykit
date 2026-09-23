"""Render FastAPI and Starlette failures as RFC 9457 problem responses.

Register application exception mappings before installing the handlers so
Starlette dispatches them through its typed exception middleware. The fallback
handler also logs the current trace id.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rn_forge.web import (
    PROBLEM_MEDIA_TYPE,
    REQUIRED_FIELD_DETAIL,
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemType,
    current_trace_id,
    default_registry,
    field_error,
    render_problem,
)

__all__ = ["Log", "register_problem_handlers"]

type Log = Callable[[str, Mapping[str, Any]], None]
"""The injected logging sink, called as ``log(event, context)``."""


def register_problem_handlers(
    app: FastAPI,
    *,
    registry: ProblemRegistry | None = None,
    realm: str | None = None,
    log: Log | None = None,
) -> None:
    """Render every error *app* produces as ``application/problem+json``.

    Args:
        app: The application. Call this once while building it; nothing is
            registered on import.
        registry: The rows to render with. Defaults to a fresh
            :func:`rn_forge.web.default_registry`. ``RequestValidationError`` is
            registered on it against ``validation-error``/422 unless it already
            has a row.
        realm: The ``realm`` of the ``WWW-Authenticate`` challenge a 401
            carries when the exception brought none of its own. A 403 never
            carries one.
        log: Called as ``log("problem.server_error", context)`` for every 5xx,
            with the exception under ``"exc"``. The body carries no detail, so
            this is the only place the cause goes.
    """
    rows = registry if registry is not None else default_registry()
    if RequestValidationError not in rows.rows():
        rows.register(RequestValidationError, VALIDATION_ERROR)

    def respond(
        request: Request,
        exc: Exception,
        *,
        problem: ProblemType | None = None,
        detail: str | None = None,
        extensions: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JSONResponse:
        rendered = render_problem(
            rows,
            exc,
            instance=request.url.path,
            problem=problem,
            detail=detail,
            extensions=extensions,
            headers=headers,
            realm=realm,
        )
        if rendered.status >= 500 and log is not None:
            log(
                "problem.server_error",
                {
                    "exc": exc,
                    "status": rendered.status,
                    "instance": rendered.problem.instance,
                    "trace_id": current_trace_id(),
                },
            )
        return JSONResponse(
            rendered.body,
            status_code=rendered.status,
            media_type=PROBLEM_MEDIA_TYPE,
            headers=dict(rendered.headers),
        )

    async def on_exception(request: Request, exc: Exception) -> JSONResponse:
        return respond(request, exc)

    async def on_http_exception(request: Request, exc: Exception) -> JSONResponse:
        http = cast("StarletteHTTPException", exc)
        row = rows.problem_for_status(http.status_code)
        return respond(
            request,
            exc,
            problem=row,
            detail=http.detail if row.status < 500 else None,
            headers=http.headers,
        )

    async def on_validation_error(request: Request, exc: Exception) -> JSONResponse:
        errors = cast("RequestValidationError", exc).errors()
        return respond(
            request,
            exc,
            detail=rows.problem_for(exc).title,
            extensions={"errors": _validation_errors(errors)},
        )

    for exc_type in rows.rows():
        if issubclass(exc_type, Exception):
            app.add_exception_handler(exc_type, on_exception)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(Exception, on_exception)


def _validation_errors(raw: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Map pydantic's ``errors()`` list to :func:`rn_forge.web.field_error` entries.

    FastAPI's leading ``"body"`` location is dropped, and a missing field reads
    :data:`rn_forge.web.REQUIRED_FIELD_DETAIL` as it does on DRF.
    """
    return [
        field_error(
            _body_relative(entry.get("loc") or ()),
            REQUIRED_FIELD_DETAIL
            if entry.get("type") == "missing"
            else str(entry.get("msg", "")),
        )
        for entry in raw
    ]


def _body_relative(loc: Sequence[Any]) -> Sequence[Any]:
    return loc[1:] if loc and loc[0] == "body" else loc
