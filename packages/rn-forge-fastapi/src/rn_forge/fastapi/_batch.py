"""Checks and validates a batch request body: the guards and the threaded JSON route."""

import json
from collections.abc import Callable, Coroutine, Mapping, Sequence
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.params import Depends as DependsParam
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import (
    BaseModel,
    SkipValidation,
    TypeAdapter,
    ValidationError,
    create_model,
)
from rn_forge.web import (
    NULL_FIELD_DETAIL,
    REQUIRED_FIELD_DETAIL,
    RowsInvalid,
)
from rn_forge.web.transfer import NON_EMPTY_LIST_DETAIL, RowError, row_cap_problem


def list_model(
    name: str, member: str, item: Any, *, validate_items: bool = True
) -> type[BaseModel]:
    """Build ``{member: [item]}``, the schema FastAPI documents and validates."""
    make = cast("Callable[..., type[BaseModel]]", create_model)
    # The guard has already validated each item; FastAPI would do it again.
    items = list[item] if validate_items else Annotated[list[item], SkipValidation]
    return make(name, **{member: (items, ...)})


def rejection(loc: str, kind: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": kind, "loc": ("body", loc), "msg": message}]
    )


def error_message(err: Mapping[str, Any]) -> str:
    if err["type"] == "missing":
        return REQUIRED_FIELD_DETAIL
    if "input" in err and err["input"] is None:
        return NULL_FIELD_DETAIL
    if err["type"] == "value_error" and "ctx" in err:
        return str(err["ctx"]["error"])
    return err["msg"]


def item_errors(index: int, exc: ValidationError) -> list[RowError]:
    return [
        RowError(index, ".".join(str(part) for part in err["loc"]), error_message(err))
        for err in exc.errors()
    ]


async def checked_list(
    request: Request, key: str, max_rows: int | None
) -> list[object]:
    """Return the raw body's *key* member, which must be a non-empty list within *max_rows*."""
    try:
        body: object = await request.json()
    except ValueError:
        body = None
    members: Mapping[str, object] = (
        cast("Mapping[str, object]", body) if isinstance(body, Mapping) else {}
    )
    if key not in members:
        raise rejection(key, "missing", "Field required")
    value: object = members[key]
    if not isinstance(value, list) or not value:
        raise rejection(key, "value_error", NON_EMPTY_LIST_DETAIL)
    entries = cast("list[object]", value)
    if max_rows is not None and len(entries) > max_rows:
        raise ValueError(
            row_cap_problem("batch", max_rows, instance=request.url.path).problem.detail
        )
    return entries


def list_guard(key: str, max_rows: int | None) -> DependsParam:
    """Check the raw body's *key* member before FastAPI validates the body."""

    async def guard(request: Request) -> None:
        await checked_list(request, key, max_rows)

    return Depends(guard)


def validate_items[T: BaseModel](
    items: TypeAdapter[T], entries: Sequence[object]
) -> tuple[list[T], list[RowError]]:
    valid: list[T] = []
    errors: list[RowError] = []
    for index, item in enumerate(entries):
        try:
            valid.append(items.validate_python(item))
        except ValidationError as exc:
            errors.extend(item_errors(index, exc))
    return valid, errors


def models_guard[T: BaseModel](
    key: str, max_rows: int | None, item_model: type[T]
) -> Any:
    """Check the body's *key* member, validate each item into *item_model* and yield the models.

    Runs before FastAPI validates the body. The checks fire in the order the
    wire contract states, and item failures use the row-error wording.
    """
    items = TypeAdapter(item_model)

    async def guard(request: Request) -> list[T]:
        entries = await checked_list(request, key, max_rows)
        valid, errors = await run_in_threadpool(validate_items, items, entries)
        if errors:
            raise RowsInvalid(errors, root=key)
        return valid

    return Depends(guard)


class ThreadedJsonRequest(Request):
    """A request whose JSON body is parsed in a worker thread."""

    async def json(self) -> Any:
        if not hasattr(self, "_json"):
            self._json = await run_in_threadpool(json.loads, await self.body())
        return self._json


class ThreadedJsonRoute(APIRoute):
    """A route that reads its request body through :class:`ThreadedJsonRequest`."""

    # FastAPI parses the body before any dependency runs, so the route has to
    # swap the request class to move that parse off the event loop.
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            return await handler(ThreadedJsonRequest(request.scope, request.receive))

        return route
