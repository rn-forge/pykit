"""A route decorator over :func:`rn_forge.web.run_idempotent_async`."""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Concatenate

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from rn_forge.web import (
    IDEMPOTENCY_KEY_HEADER,
    AsyncIdempotencyStore,
    run_idempotent_async,
)

__all__ = ["idempotent"]


def idempotent[**P](
    store: AsyncIdempotencyStore,
    *,
    scope: str,
    header: str = IDEMPOTENCY_KEY_HEADER,
) -> Callable[
    [Callable[Concatenate[Request, P], Awaitable[Response]]],
    Callable[Concatenate[Request, P], Awaitable[Response]],
]:
    """Decorate an async route so an unsafe request executes once per key.

    The decorated route must declare ``request: Request`` as a parameter —
    FastAPI injects it like any other dependency — and must return a
    :class:`~fastapi.responses.Response` whose body is JSON. Safe methods
    bypass the store. A missing key on an unsafe method raises
    :class:`rn_forge.web.IdempotencyKeyRequired` (400); a replay returns the
    stored status and body verbatim; the same key with a different body
    raises :class:`rn_forge.web.IdempotencyKeyReuse` (422); a duplicate while
    the original is still in flight raises
    :class:`rn_forge.web.IdempotencyKeyInFlight` (409).

    Example::

        @app.post("/charges", status_code=201)
        @idempotent(store, scope="charges")
        async def create_charge(request: Request, body: Charge) -> JSONResponse:
            ...
    """

    def decorate(
        handler: Callable[Concatenate[Request, P], Awaitable[Response]],
    ) -> Callable[Concatenate[Request, P], Awaitable[Response]]:
        @functools.wraps(handler)
        async def wrapper(
            request: Request, *args: P.args, **kwargs: P.kwargs
        ) -> Response:
            # The runner returns (status, body); the original Response object
            # — headers included — is kept here for the non-replayed case.
            executed: list[Response] = []

            async def execute() -> tuple[int, Mapping[str, Any]]:
                response = await handler(request, *args, **kwargs)
                executed.append(response)
                return response.status_code, json.loads(bytes(response.body))

            raw_body = await request.body()
            result = await run_idempotent_async(
                store,
                scope=scope,
                key=request.headers.get(header),
                method=request.method,
                body=json.loads(raw_body) if raw_body else None,
                execute=execute,
                header=header,
            )
            if result.replayed:
                return JSONResponse(dict(result.body), status_code=result.status)
            return executed[0]

        return wrapper

    return decorate
