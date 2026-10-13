"""FastAPI dependency and helper for the ``readMask`` query parameter."""

from __future__ import annotations

import types
from collections.abc import Callable, Sequence
from collections.abc import Set as AbstractSet
from typing import Annotated, Any, Union, cast, get_args, get_origin

from fastapi import Query
from pydantic import BaseModel

from rn_forge.web import READ_MASK_PARAM, FieldTree, Page, ReadMask, parse_read_mask

__all__ = ["masked", "read_mask_param"]


def read_mask_param(model: type[BaseModel]) -> Callable[..., ReadMask | None]:
    """Return a dependency yielding the parsed ``readMask``, or ``None`` for the whole resource.

    The declared fields are *model*'s serialization aliases, including its
    computed fields. A field typed as a model, ``Model | None`` or ``list[Model]``
    is a nested object whose own fields can be selected; any other field,
    including a ``dict``, is a leaf. A path that names no declared field, or
    that combines ``*`` with other paths, is a 400 before the route runs.

    Apply the result with ``mask.apply(body)`` to a dumped resource, or with
    :func:`masked` to a page.

    Args:
        model: The model of one resource, as the route serves it.
    """
    fields = _field_tree(model, frozenset())

    def dependency(
        read_mask: str | None = Query(
            default=None,
            alias=READ_MASK_PARAM,
            description=(
                "Comma-separated field paths to return, such as "
                "`displayName,address.city`. `*` returns the whole resource."
            ),
        ),
    ) -> ReadMask | None:
        return parse_read_mask(read_mask, fields=fields)

    return dependency


def masked(page: Page[Any], mask: ReadMask | None) -> dict[str, Any]:
    """Return the wire body of *page* with *mask* applied to each of its items.

    ``nextPageToken`` and ``totalSize`` are left alone. With no mask the body is
    the page's own.
    """
    body = page.as_body()
    if mask is None:
        return body
    items = cast("list[Any]", body["items"])
    return {**body, "items": [mask.apply(item) for item in items]}


def _field_tree(model: type[BaseModel], path: frozenset[type]) -> FieldTree:
    tree: dict[str, FieldTree | None] = {}
    for name, info in model.model_fields.items():
        key = info.serialization_alias or info.alias or name
        tree[key] = _nested(info.annotation, path | {model})
    for name, computed in model.model_computed_fields.items():
        tree[computed.alias or name] = None
    return tree


def _nested(annotation: Any, path: frozenset[type]) -> FieldTree | None:
    """The fields of the model *annotation* holds, directly or in a list or optional; else ``None``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        # A model that contains itself has no finite tree, so it stops at a leaf.
        return None if annotation in path else _field_tree(annotation, path)
    origin = get_origin(annotation)
    args: tuple[Any, ...] = get_args(annotation)
    if origin is Annotated:
        return _nested(args[0], path)
    if origin in (Union, types.UnionType):
        present = [arg for arg in args if arg is not type(None)]
        return _nested(present[0], path) if len(present) == 1 else None
    if isinstance(origin, type) and issubclass(origin, (Sequence, AbstractSet)):
        return _nested(args[0], path) if args else None
    return None
