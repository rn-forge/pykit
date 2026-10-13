"""RFC 7396 JSON Merge Patch.

Hand-rolled: no clearly maintained package implements RFC 7396, and the algorithm is a few lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from rn_forge.web.exceptions import InvalidMergePatch

__all__ = [
    "MERGE_PATCH_MEDIA_TYPE",
    "JsonValue",
    "apply_merge_patch",
    "merge_representation",
    "require_patch_object",
]

MERGE_PATCH_MEDIA_TYPE: Final = "application/merge-patch+json"
"""The media type of a JSON Merge Patch body."""

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


def apply_merge_patch(target: JsonValue, patch: JsonValue) -> JsonValue:
    """Apply *patch* to *target* as RFC 7396 section 2 specifies.

    A non-object *patch* replaces *target*. An object *patch* merges into *target*
    (an empty object when *target* is not one): a ``null`` member removes the
    member, any other member is merged recursively, and arrays are replaced whole.

    Args:
        target: The document to patch. Not modified.
        patch: The merge patch. Not modified.

    Returns:
        The patched document, sharing no mutable state with either argument.
    """
    if not isinstance(patch, dict):
        return _copy(patch)
    result: dict[str, JsonValue] = (
        {key: _copy(value) for key, value in target.items()}
        if isinstance(target, dict)
        else {}
    )
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = apply_merge_patch(result.get(key), value)
    return result


def merge_representation(
    current: Mapping[str, JsonValue], patch: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    """Merge *patch* into the resource representation *current*.

    At the top level a ``null`` member sets that field to ``None`` and keeps it.
    Every other member, and everything below the top level, follows
    :func:`apply_merge_patch`.

    Args:
        current: The resource's current representation. Not modified.
        patch: The merge patch object. Not modified.

    Returns:
        The merged representation.
    """
    merged = {key: _copy(value) for key, value in current.items()}
    for key, value in patch.items():
        merged[key] = (
            None if value is None else apply_merge_patch(merged.get(key), value)
        )
    return merged


def require_patch_object(body: object) -> dict[str, JsonValue]:
    """Return *body* when it is a JSON object.

    Raises:
        InvalidMergePatch: *body* is not a JSON object.
    """
    if not isinstance(body, dict):
        raise InvalidMergePatch
    return body  # pyright: ignore[reportUnknownVariableType]


def _copy(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value
