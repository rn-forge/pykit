"""Exception handlers: every error a FastAPI application produces is an RFC 9457 problem.

The single highest-value adapter in the package. An application that skips it
has two error formats — its own, and FastAPI's ``{"detail": ...}``.

:func:`register_problem_handlers` installs handlers for four sources of error,
and every body is built by :class:`rn_forge.web.ProblemRegistry`; nothing here
decides a slug, a status or a detail:

1. **Every exception type the registry knows**, one handler per type.
2. **Starlette's ``HTTPException``** — a routing 404, a 405 — through
   :meth:`rn_forge.web.ProblemRegistry.problem_for_status`.
3. **``RequestValidationError``**, normalized through
   :func:`rn_forge.web.errors_from_pointer_list`.
4. **Bare ``Exception``** — a 500 whose body says nothing and whose ``log``
   says everything.

Why one handler per registered type, not one on ``Exception``
-------------------------------------------------------------

Starlette sends a handler keyed on ``Exception`` to its outermost
``ServerErrorMiddleware``, which writes the response and then **re-raises**:
every 409 would print a traceback and fail a ``TestClient`` test. Keyed on the
exception's own class, the handler runs in ``ExceptionMiddleware`` instead,
which swallows the exception and sits *inside* user middleware, so the
correlation header is stamped on the way out. Hence: **register an
application's exceptions on the registry before calling this.** A row added
afterwards still renders correctly, but through the ``Exception`` path.

That path is outside every user middleware, so the handler stamps the
correlation header itself. It still finds the ID: the middleware binds it
without resetting (see :mod:`rn_forge.web.context`). With no middleware
installed at all, the body is still a valid problem whose ``correlation_id`` is
``null``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    DEFAULT_CORRELATION_HEADER,
    PROBLEM_MEDIA_TYPE,
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemType,
    challenge_header,
    default_registry,
    errors_from_pointer_list,
    get_correlation_id,
)
from rn_forge.web.context import CORRELATION_ID_KEY

__all__ = ["Log", "register_problem_handlers"]

type Log = Callable[[str, Mapping[str, Any]], None]
"""The injected logging sink, called as ``log(event, context)``."""


def register_problem_handlers(
    app: FastAPI,
    *,
    registry: ProblemRegistry | None = None,
    realm: str | None = None,
    correlation_header: str = DEFAULT_CORRELATION_HEADER,
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
        realm: The ``realm`` of the ``WWW-Authenticate`` challenge every 401
            carries. A 403 never carries one.
        correlation_header: The header the correlation ID is stamped on. Match
            the middleware's ``header_name``.
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
        row = problem if problem is not None else rows.problem_for(exc)
        correlation_id = get_correlation_id()
        body = rows.build(
            exc,
            instance=request.url.path,
            # A 401 says only that authentication failed; the reason was logged
            # where the credentials were checked.
            detail=AUTH_FAILED_DETAIL if row.status == 401 else detail,
            problem=row,
            extensions={CORRELATION_ID_KEY: correlation_id, **(extensions or {})},
        )
        if row.status >= 500 and log is not None:
            log(
                "problem.server_error",
                {
                    "exc": exc,
                    "status": row.status,
                    "instance": body.instance,
                    CORRELATION_ID_KEY: correlation_id,
                },
            )
        response_headers = dict(headers or {})
        if row.status == 401:
            response_headers["WWW-Authenticate"] = challenge_header(realm=realm)
        if correlation_id is not None:
            response_headers[correlation_header] = correlation_id
        return JSONResponse(
            body.as_body(),
            status_code=body.status,
            media_type=PROBLEM_MEDIA_TYPE,
            headers=response_headers,
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
            extensions={"errors": errors_from_pointer_list(errors)},
        )

    for exc_type in rows.rows():
        if issubclass(exc_type, Exception):
            app.add_exception_handler(exc_type, on_exception)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(Exception, on_exception)
