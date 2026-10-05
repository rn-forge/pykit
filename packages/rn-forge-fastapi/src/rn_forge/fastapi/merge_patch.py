"""FastAPI binding for JSON Merge Patch (RFC 7396).

On a ``PATCH`` route, declare :func:`merge_patch_body` before ``require_if_match``, call
:func:`rn_forge.web.check_precondition` in the route, then merge the body into the stored
resource with :func:`merge_into`. Add :func:`merge_patch_openapi` as the route's
``openapi_extra``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from rn_forge.web import (
    MERGE_PATCH_MEDIA_TYPE,
    InvalidMergePatch,
    UnsupportedMediaType,
    merge_representation,
    require_patch_object,
)

__all__ = ["merge_into", "merge_patch_body", "merge_patch_openapi"]


def merge_patch_body() -> Callable[..., Any]:
    """Return a dependency yielding the raw request body.

    The dependency raises :class:`rn_forge.web.UnsupportedMediaType` (415, with
    ``Accept-Patch``) unless the request's media type, ignoring parameters, is
    ``application/merge-patch+json``. The body is returned as bytes, unparsed; pass it to
    :func:`merge_into`.
    """

    async def dependency(request: Request) -> bytes:
        media_type = request.headers.get("content-type", "").split(";")[0].strip()
        if media_type.lower() != MERGE_PATCH_MEDIA_TYPE:
            raise UnsupportedMediaType()
        return await request.body()

    return dependency


def merge_into[M: BaseModel](model: type[M], current: object, body: bytes) -> M:
    """Merge the merge-patch *body* into *current* and return the validated *model*.

    *body* is parsed as JSON and must be an object. *current* is dumped through *model* by alias, merged with
    :func:`rn_forge.web.merge_representation`, and the result validated as a full document.

    Args:
        model: The pydantic model of the resource.
        current: The stored resource: a mapping or an object with matching attributes.
        body: The raw request body from :func:`merge_patch_body`.

    Raises:
        rn_forge.web.InvalidMergePatch: *body* is not valid JSON or not a JSON object.
        fastapi.exceptions.RequestValidationError: The merged document is invalid. Each error's
            location is prefixed with ``"body"``.
    """
    try:
        patch = require_patch_object(json.loads(body))
    except ValueError:
        raise InvalidMergePatch() from None
    representation = model.model_validate(current, from_attributes=True).model_dump(
        by_alias=True, mode="json"
    )
    merged = merge_representation(representation, patch)
    try:
        return model.model_validate(merged)
    except ValidationError as exc:
        raise RequestValidationError(
            [
                {**error, "loc": ("body", *error["loc"])}
                for error in exc.errors(include_url=False, include_context=False)
            ]
        ) from exc


def merge_patch_openapi() -> dict[str, Any]:
    """Return the ``openapi_extra`` declaring a merge-patch request body."""
    return {
        "requestBody": {
            "required": True,
            "content": {MERGE_PATCH_MEDIA_TYPE: {"schema": {"type": "object"}}},
        }
    }
