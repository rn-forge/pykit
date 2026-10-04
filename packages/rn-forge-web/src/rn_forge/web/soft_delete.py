"""Soft delete: the ``showDeleted`` parameter and the live-resource guard (AIP-164)."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from rn_forge.web.exceptions import ResourceDeleted

__all__ = [
    "SHOW_DELETED_PARAM",
    "require_live",
]

SHOW_DELETED_PARAM: Final = "showDeleted"
"""The name of the query parameter that includes soft-deleted resources in a list."""


def require_live(delete_time: datetime | None, *, label: str, id: object) -> None:
    """Raise :class:`~rn_forge.web.ResourceDeleted` when the resource is soft-deleted.

    Args:
        delete_time: The resource's ``delete_time``; ``None`` while it is live.
        label: The resource's display name, such as ``Note``.
        id: The resource identifier.

    Raises:
        ResourceDeleted: *delete_time* is not ``None``.
    """
    if delete_time is not None:
        raise ResourceDeleted(label, id)
