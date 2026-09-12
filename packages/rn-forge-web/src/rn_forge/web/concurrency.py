"""Optimistic concurrency: ETag validators and the ``If-Match`` precondition.

An entity's ``version`` column becomes an ETag; the client sends it back as
``If-Match`` on the next write; the server refuses the write if the version has
moved. This module owns the validator format and the precondition check, and
nothing else — turning a version into a ``WHERE`` clause is the ORM's job.

Status codes, and they are not a judgement call
-----------------------------------------------

- **412 Precondition Failed** when the client's precondition evaluated to false
  (RFC 9110 §15.5.13 defines exactly that).
- **428 Precondition Required** when the route demands a precondition and the
  client sent none (RFC 6585 §3).
- **400** when the header is present but unparseable.

Not 409 for a mismatch: 409 is for a conflict with the resource's state
generally, which is a superset. A consumer that genuinely needs 409 here
re-registers :class:`~rn_forge.web.exceptions.VersionConflict` on its own
registry instance — one line, which is the payoff for the registry being
instantiable. No application should need to.

Strong validators are rejected
------------------------------

Both codecs emit and accept only the **weak** form, ``W/"..."``. A strong
validator asserts byte-for-byte equality of the representation, and a version
counter does not: two responses at the same version can differ in a
``Content-Type`` or a computed field. A bare ``"7"`` is therefore a
:class:`~rn_forge.web.exceptions.MalformedPrecondition`, not a silently
accepted synonym. ``If-Match: *`` is accepted, as RFC 9110 §13.1.1 requires.
"""

from __future__ import annotations

import re
from typing import Final, Protocol, runtime_checkable

from rn_forge.web.exceptions import (
    MalformedPrecondition,
    PreconditionRequired,
    VersionConflict,
)

__all__ = [
    "ANY_ETAG",
    "ETagCodec",
    "EntityVersionETagCodec",
    "VersionETagCodec",
    "check_precondition",
]

ANY_ETAG: Final = "*"
"""``If-Match: *`` — matches any current representation (RFC 9110 §13.1.1)."""


@runtime_checkable
class ETagCodec(Protocol):
    """Formats and parses the ETag validator carried in ``If-Match``."""

    def format(self, *, entity_id: object, version: int) -> str:
        """Return the ETag validator for an entity at a version."""
        ...

    def parse(self, raw: str) -> tuple[str | None, int]:
        """Parse a validator into ``(entity_id or None, version)``.

        Raises:
            MalformedPrecondition: *raw* is not a validator this codec emits.
        """
        ...


_VERSION_RE: Final = re.compile(r'^W/"(?P<version>\d+)"$')
_ENTITY_VERSION_RE: Final = re.compile(r'^W/"(?P<entity>[^:"]+):(?P<version>\d+)"$')


class VersionETagCodec:
    """``W/"<version>"`` — carries no entity identity.

    For models without a stable public id to put in the validator. It cannot
    catch a precondition replayed from a different entity; prefer
    :class:`EntityVersionETagCodec` where an id is available.
    """

    def format(self, *, entity_id: object, version: int) -> str:
        """Return ``W/"<version>"``. *entity_id* is accepted and ignored."""
        del entity_id
        return f'W/"{version}"'

    def parse(self, raw: str) -> tuple[str | None, int]:
        """Parse ``W/"<version>"`` into ``(None, version)``."""
        match = _VERSION_RE.match(raw.strip())
        if match is None:
            raise MalformedPrecondition(
                "Malformed If-Match validator: {}", raw, error_code=400
            )
        return None, int(match["version"])


class EntityVersionETagCodec:
    """``W/"<entity_id>:<version>"`` — the default.

    Carrying the entity id catches a client replaying a precondition from a
    *different* entity, which the version alone cannot.

    The entity segment is deliberately **any run of characters that is not a
    colon or a quote**, not a UUID pattern: integer and slug primary keys are
    both real, and ``rn_forge.django.BaseModel`` does not have a UUID pk. That
    relaxation is intentional.
    """

    def format(self, *, entity_id: object, version: int) -> str:
        """Return ``W/"<entity_id>:<version>"``.

        Raises:
            MalformedPrecondition: *entity_id* renders with a ``:`` or ``"``,
                which would produce a validator this codec cannot parse back.
        """
        rendered = str(entity_id)
        if ":" in rendered or '"' in rendered:
            raise MalformedPrecondition(
                "Entity id {!r} cannot appear in an ETag validator", rendered
            )
        return f'W/"{rendered}:{version}"'

    def parse(self, raw: str) -> tuple[str | None, int]:
        """Parse ``W/"<entity_id>:<version>"`` into ``(entity_id, version)``."""
        match = _ENTITY_VERSION_RE.match(raw.strip())
        if match is None:
            raise MalformedPrecondition(
                "Malformed If-Match validator: {}", raw, error_code=400
            )
        return match["entity"], int(match["version"])


DEFAULT_CODEC: Final[ETagCodec] = EntityVersionETagCodec()
"""The codec :func:`check_precondition` uses when the caller names none."""


def check_precondition(
    raw_if_match: str | None,
    *,
    current_version: int,
    entity_id: object | None = None,
    codec: ETagCodec = DEFAULT_CODEC,
    required: bool = False,
) -> None:
    """Raise unless the client's precondition matches the current state.

    Deliberately strict about the validator's syntax: anything it cannot parse
    is a 400, never a crash.

    Args:
        raw_if_match: The raw ``If-Match`` header value, or ``None``.
        current_version: The entity's current version.
        entity_id: The entity's id, compared when the codec carries one.
        codec: The validator format. Defaults to :class:`EntityVersionETagCodec`.
        required: When ``True``, an absent header is an error. Making
            preconditions mandatory is the caller's choice, per route.

    Raises:
        PreconditionRequired: *raw_if_match* is ``None`` and *required*.
        MalformedPrecondition: The header is present but unparseable.
        VersionConflict: The version, or the entity id, does not match.
    """
    if raw_if_match is None:
        if required:
            raise PreconditionRequired(
                "This endpoint requires an If-Match precondition", error_code=428
            )
        return

    candidate = raw_if_match.strip()
    if candidate == ANY_ETAG:
        # RFC 9110: `*` matches any current representation. Both surveyed
        # implementations got this wrong; it costs two lines.
        return

    parsed_entity, parsed_version = codec.parse(candidate)
    if parsed_version != current_version:
        raise VersionConflict(
            "Precondition failed: expected version {}, got {}",
            current_version,
            parsed_version,
            error_code=412,
        )
    if parsed_entity is not None and entity_id is not None:
        if parsed_entity != str(entity_id):
            raise VersionConflict(
                "Precondition failed: validator is for entity {}, not {}",
                parsed_entity,
                entity_id,
                error_code=412,
            )
