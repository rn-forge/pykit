"""Opaque cursor pagination and ``orderBy`` using Google AIP-158 and AIP-132.

Page sizes are clamped to the configured cap. Responses use ``items``,
``nextPageToken``, and the optional ``totalSize`` field.

No pagination library is adopted: ``fastapi-pagination`` 0.16.0 (checked 2026-09-23) cannot produce
``{items, nextPageToken}`` without ``total`` from its stock cursor page, and its ``CursorParams``
reject an oversized page size with a 422 where AIP-158 clamps.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote

from pydantic import ConfigDict, Field

from rn_forge.web.exceptions import InvalidCursor, InvalidOrderBy
from rn_forge.web.models import WireModel

__all__ = [
    "DEFAULT_PAGE_SIZE_PARAM",
    "DEFAULT_PAGE_TOKEN_PARAM",
    "ORDER_BY_PARAM",
    "Cursor",
    "OrderField",
    "Page",
    "check_cursor_order",
    "clamp_page_size",
    "decode_cursor",
    "encode_cursor",
    "format_order_by",
    "next_link_header",
    "parse_order_by",
]

DEFAULT_PAGE_SIZE_PARAM: Final = "pageSize"
"""The query parameter carrying the requested page size."""

DEFAULT_PAGE_TOKEN_PARAM: Final = "pageToken"
"""The query parameter carrying the continuation token."""

ORDER_BY_PARAM: Final = "orderBy"
"""The query parameter carrying the sort order."""

_SORT_KEY: Final = "k"
_ENTITY_ID: Final = "id"
_ORDER_BY: Final = "o"


@dataclass(frozen=True)
class Cursor:
    """The decoded contents of a page token.

    ``sort_key`` is the value of the column the query orders by; ``entity_id``
    is the tiebreaker that makes the ordering total. Together they are the
    keyset the next page resumes from. ``order_by`` is the canonical
    ``orderBy`` the token was issued for, empty for the endpoint's default order.
    """

    sort_key: str
    entity_id: str
    order_by: str = ""


@dataclass(frozen=True)
class OrderField:
    """One ``orderBy`` term: a field name as it appears on the wire and a direction."""

    field: str
    descending: bool = False


def parse_order_by(
    raw: str | None, *, allowed: Collection[str]
) -> tuple[OrderField, ...]:
    """Parse an AIP-132 ``orderBy`` value such as ``displayName desc``.

    A term is a field name optionally followed by ``asc`` or ``desc`` (default
    ``asc``). One term is accepted: the page token holds one sort value, so a
    list cannot yet be paged by several. The result is a tuple so that several
    terms can be returned without changing the signature.

    Args:
        raw: The query parameter value. ``None`` or blank yields no terms.
        allowed: The field names the endpoint can sort by, as they appear on
            the wire.

    Returns:
        The single term, or an empty tuple when *raw* is blank.

    Raises:
        InvalidOrderBy: *raw* has more than one term, or the term is malformed
            or names a field outside *allowed*.
    """
    if raw is None or not raw.strip():
        return ()
    chunks = raw.split(",")
    if len(chunks) > 1:
        raise InvalidOrderBy(
            f"orderBy accepts one field; got {len(chunks)}", error_code=400
        )
    terms: list[OrderField] = []
    for chunk in chunks:
        parts = chunk.split()
        if len(parts) not in (1, 2) or (
            len(parts) == 2 and parts[1] not in ("asc", "desc")
        ):
            raise InvalidOrderBy(
                f"Malformed orderBy term {chunk.strip()!r}", error_code=400
            )
        name = parts[0]
        if name not in allowed:
            raise InvalidOrderBy(
                f"Cannot order by {name!r}; allowed: {', '.join(sorted(allowed))}",
                error_code=400,
            )
        terms.append(
            OrderField(name, descending=len(parts) == 2 and parts[1] == "desc")
        )
    return tuple(terms)


def format_order_by(terms: Collection[OrderField]) -> str:
    """Return the canonical ``orderBy`` string for *terms* (``desc`` explicit, ``asc`` omitted)."""
    return ",".join(f"{t.field} desc" if t.descending else t.field for t in terms)


def check_cursor_order(cursor: Cursor, terms: Collection[OrderField]) -> None:
    """Reject a page token issued for a different ordering than *terms*.

    Raises:
        InvalidCursor: The token's order differs from the request's.
    """
    if cursor.order_by != format_order_by(terms):
        raise InvalidCursor("pageToken does not match orderBy", error_code=400)


def encode_cursor(sort_key: str, entity_id: str, order_by: str = "") -> str:
    """Encode a keyset position as an opaque page token.

    URL-safe base64 over compact JSON — small, and safe in a query string
    without further escaping. *order_by* is the canonical ordering from
    :func:`format_order_by`; it is omitted from the token when empty.
    """
    fields = {_SORT_KEY: sort_key, _ENTITY_ID: entity_id}
    if order_by:
        fields[_ORDER_BY] = order_by
    payload = json.dumps(fields, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(raw: str) -> Cursor:
    """Decode a page token.

    Every malformed input class is caught — not base64, base64 of non-JSON,
    JSON of a non-object, JSON missing a key. Missing one of them turns a
    tampered token into a 500.

    Raises:
        InvalidCursor: *raw* is not a well-formed page token.
    """
    try:
        decoded = base64.urlsafe_b64decode(raw.encode())
        payload = json.loads(decoded)
        return Cursor(
            sort_key=str(payload[_SORT_KEY]),
            entity_id=str(payload[_ENTITY_ID]),
            order_by=str(payload.get(_ORDER_BY, "")),
        )
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise InvalidCursor("Malformed page token", error_code=400) from exc


def _is_none(value: object) -> bool:
    return value is None


class Page[T](WireModel):
    """One page of results, in the AIP-158 envelope.

    ``nextPageToken`` is always present and ``null`` on the last page;
    ``totalSize`` is omitted from the body when absent.
    """

    model_config = ConfigDict(frozen=True)

    items: list[T]
    next_page_token: str | None
    total_size: int | None = Field(default=None, exclude_if=_is_none)

    def as_body(self) -> dict[str, Any]:
        """Return the wire body, camelCase, omitting an absent ``totalSize``."""
        return self.model_dump()


def clamp_page_size(requested: int | None, *, default: int, cap: int) -> int:
    """Return a usable page size, clamping rather than rejecting.

    Per AIP-158, an over-large ``pageSize`` is coerced to the maximum.

    Args:
        requested: What the client asked for. ``None`` or a non-positive value
            means "unspecified" and yields *default*.
        default: The size used when the client asks for none.
        cap: The largest size this endpoint will serve.

    Returns:
        A size in ``1..cap``.
    """
    if requested is None or requested <= 0:
        return min(default, cap)
    return min(requested, cap)


def next_link_header(
    base_url: str, token: str, *, param: str = DEFAULT_PAGE_TOKEN_PARAM
) -> str:
    """Build an RFC 8288 ``Link: <...>; rel="next"`` header value.

    Additive, never a replacement: ``nextPageToken`` in the body is the
    contract, and this header is a convenience for clients that were not
    generated from the schema. A client relying only on the header will break
    on an endpoint that cannot build an absolute URL.

    Args:
        base_url: The collection URL, with or without an existing query string.
        token: The continuation token to embed.
        param: The query parameter name.

    Returns:
        A value suitable for the ``Link`` response header.
    """
    separator = "&" if "?" in base_url else "?"
    return f'<{base_url}{separator}{param}={quote(token, safe="")}>; rel="next"'
