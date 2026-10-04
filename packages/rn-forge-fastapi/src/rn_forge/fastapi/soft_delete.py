"""Soft delete over FastAPI (AIP-164): ``DELETE`` and ``:undelete`` routes and ``showDeleted``.

Persistence is the application's: :func:`soft_delete_router` takes a store
dependency that implements :class:`SoftDeleteStore`.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.params import Depends as DependsParam
from pydantic import BaseModel
from rn_forge.fastapi.openapi import operation_id
from rn_forge.web import (
    SHOW_DELETED_PARAM,
    ETagCodec,
    ResourceNotDeleted,
    VersionETagCodec,
    check_precondition,
    parse_flag,
)

__all__ = [
    "SoftDeleteState",
    "SoftDeleteStore",
    "show_deleted_param",
    "soft_delete_router",
]


@dataclass(frozen=True)
class SoftDeleteState:
    """A row as :class:`SoftDeleteStore` reports it.

    Attributes:
        row: The stored row.
        version: The row's version, or ``None`` when the resource is unversioned.
        delete_time: When the row was soft-deleted; ``None`` while it is live.
    """

    row: Any
    version: int | None
    delete_time: datetime | None


class SoftDeleteStore(Protocol):
    """Finds, soft-deletes and restores one resource.

    The store owns the transaction and supplies the time recorded as
    ``delete_time``.
    """

    async def find(self, id: str) -> SoftDeleteState | None:
        """Return the row with *id*, deleted or not, or ``None`` when it does not exist."""
        ...

    async def soft_delete(self, id: str) -> Any:
        """Soft-delete the row and return it."""
        ...

    async def undelete(self, id: str) -> Any:
        """Restore the row and return it."""
        ...


def show_deleted_param() -> Callable[..., bool]:
    """Return a dependency yielding whether the request includes soft-deleted resources.

    ``showDeleted`` is ``true`` or ``1`` (any case) to include them; any other
    value, or none, excludes them.
    """

    def dependency(
        show_deleted: str | None = Query(
            default=None,
            alias=SHOW_DELETED_PARAM,
            description="Include soft-deleted resources when `true` or `1`.",
        ),
    ) -> bool:
        return parse_flag(show_deleted)

    return dependency


def soft_delete_router(
    collection: str,
    *,
    response_model: type[BaseModel],
    resource_label: str,
    store: Callable[..., SoftDeleteStore],
    require_if_match: bool = False,
    codec: ETagCodec | None = None,
    dependencies: Sequence[DependsParam] = (),
) -> APIRouter:
    """Build ``DELETE {collection}/{id}`` and ``POST {collection}/{id}:undelete``.

    ``DELETE`` soft-deletes and answers 200 with the resource, as
    *response_model* dumped by alias. A missing or already deleted resource is a
    404 reading ``{resource_label} {id} not found``. ``:undelete`` restores the
    resource and answers 200 with it; a live resource is a 409 reading
    ``{resource_label} {id} is not deleted``.

    On a versioned resource both honour ``If-Match`` after those checks (428,
    400 or 412), and answer with the new ``ETag``. The store is not asked to
    write after a failure.

    Args:
        collection: The collection path, for example ``/notes``.
        response_model: The model of one resource.
        resource_label: The resource's name in problem details, for example ``Note``.
        store: A dependency returning the :class:`SoftDeleteStore`.
        require_if_match: When ``True``, a versioned request without
            ``If-Match`` is a 428.
        codec: The validator format; ``None`` uses
            :class:`rn_forge.web.VersionETagCodec`.
        dependencies: Dependencies of the route, as for ``APIRouter``.

    Returns:
        The router.
    """
    router = APIRouter(
        dependencies=list(dependencies), generate_unique_id_function=operation_id
    )
    etag_codec = codec or VersionETagCodec()

    def precondition(state: SoftDeleteState, id: str, if_match: str | None) -> None:
        if state.version is not None:
            check_precondition(
                if_match,
                current_version=state.version,
                entity_id=id,
                codec=etag_codec,
                required=require_if_match,
            )

    async def respond(
        target: SoftDeleteStore, id: str, row: Any, response: Response
    ) -> dict[str, Any]:
        after = await target.find(id)
        if after is not None and after.version is not None:
            response.headers["ETag"] = etag_codec.format(
                entity_id=id, version=after.version
            )
        return response_model.model_validate(row, from_attributes=True).model_dump(
            by_alias=True, mode="json"
        )

    async def soft_delete(
        id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        target: SoftDeleteStore = Depends(store),
    ) -> dict[str, Any]:
        state = await target.find(id)
        if state is None or state.delete_time is not None:
            raise LookupError(f"{resource_label} {id} not found")
        precondition(state, id, if_match)
        return await respond(target, id, await target.soft_delete(id), response)

    async def undelete(
        id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        target: SoftDeleteStore = Depends(store),
    ) -> dict[str, Any]:
        state = await target.find(id)
        if state is None:
            raise LookupError(f"{resource_label} {id} not found")
        if state.delete_time is None:
            raise ResourceNotDeleted(resource_label, id)
        precondition(state, id, if_match)
        return await respond(target, id, await target.undelete(id), response)

    router.add_api_route(
        f"{collection}/{{id}}",
        soft_delete,
        methods=["DELETE"],
        response_model=response_model,
    )
    router.add_api_route(
        f"{collection}/{{id}}:undelete",
        undelete,
        methods=["POST"],
        response_model=response_model,
    )
    return router
