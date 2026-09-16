"""``If-Match`` preconditions for DRF views over versioned models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from rest_framework.request import Request
from rn_forge.django.models.concurrency import VersionedModelMixin
from rn_forge.web import (
    ETagCodec,
    MalformedPrecondition,
    VersionETagCodec,
    check_precondition,
)

__all__ = ["enforce_version", "etag_for"]


def enforce_version(
    request: Request,
    instance: VersionedModelMixin,
    *,
    required: bool = False,
    codec: ETagCodec | None = None,
) -> None:
    """Raise unless the client's precondition matches *instance*'s current version.

    The header takes precedence over the request body's ``version`` fallback.

    Args:
        request: The DRF request.
        instance: The row being written.
        required: When ``True``, a missing precondition is a 428.
        codec: The validator format. Defaults to :class:`rn_forge.web.VersionETagCodec`,
            since ``BaseModel`` has no UUID primary key; pass
            :class:`rn_forge.web.EntityVersionETagCodec` to bind the entity id too.

    Raises:
        PreconditionRequired: Nothing was sent and *required* is set (428).
        MalformedPrecondition: The header or the body ``version`` is unparseable (400).
        VersionConflict: The version does not match (412).
    """
    resolved = codec if codec is not None else VersionETagCodec()
    raw = cast(str | None, request.headers.get("If-Match"))
    if raw is None:
        data = cast(object, request.data)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data partially untyped
        body_version = (
            cast(Mapping[str, object], data).get("version")
            if isinstance(data, Mapping)
            else None
        )
        if body_version is not None:
            raw = resolved.format(
                entity_id=instance.pk, version=_as_version(body_version)
            )
    check_precondition(
        raw,
        current_version=instance.version,
        entity_id=instance.pk,
        codec=resolved,
        required=required,
    )


def etag_for(instance: VersionedModelMixin, *, codec: ETagCodec | None = None) -> str:
    """Return the ``ETag`` response header value for *instance*."""
    resolved = codec if codec is not None else VersionETagCodec()
    return resolved.format(entity_id=instance.pk, version=instance.version)


def _as_version(value: object) -> int:
    """Parse a body ``version`` value, rejecting anything but a non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise MalformedPrecondition("Malformed version: {!r}", value, error_code=400)
    text = str(value).strip()
    if not text.isdigit():
        raise MalformedPrecondition("Malformed version: {!r}", value, error_code=400)
    return int(text)
