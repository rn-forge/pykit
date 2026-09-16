"""Opaque cursor pagination using Google AIP-158 field names.

Page sizes are clamped to the configured cap. Responses use ``items``,
``nextPageToken``, and the optional ``totalSize`` field.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote

from rn_forge.commons.lang.dataclasses import LenientDataclassMixin
from rn_forge.web.exceptions import InvalidCursor

__all__ = [
    "DEFAULT_PAGE_SIZE_PARAM",
    "DEFAULT_PAGE_TOKEN_PARAM",
    "Cursor",
    "Page",
    "clamp_page_size",
    "decode_cursor",
    "encode_cursor",
    "next_link_header",
]

DEFAULT_PAGE_SIZE_PARAM: Final = "pageSize"
"""The query parameter carrying the requested page size."""

DEFAULT_PAGE_TOKEN_PARAM: Final = "pageToken"
"""The query parameter carrying the continuation token."""

_SORT_KEY: Final = "k"
_ENTITY_ID: Final = "id"


@dataclass(frozen=True)
class Cursor:
    """The decoded contents of a page token.

    ``sort_key`` is the value of the column the query orders by; ``entity_id``
    is the tiebreaker that makes the ordering total. Together they are the
    keyset the next page resumes from.
    """

    sort_key: str
    entity_id: str


def encode_cursor(sort_key: str, entity_id: str) -> str:
    """Encode a keyset position as an opaque page token.

    URL-safe base64 over compact JSON — small, and safe in a query string
    without further escaping.
    """
    payload = json.dumps(
        {_SORT_KEY: sort_key, _ENTITY_ID: entity_id},
        separators=(",", ":"),
        sort_keys=True,
    )
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
            sort_key=str(payload[_SORT_KEY]), entity_id=str(payload[_ENTITY_ID])
        )
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise InvalidCursor("Malformed page token", error_code=400) from exc


@dataclass(frozen=True)
class Page[T](LenientDataclassMixin):
    """One page of results, in the AIP-158 envelope.

    ``total_size`` is omitted from :meth:`as_body` when absent. Lenient parsing
    is required because dacite cannot type-check the unbound ``T`` in
    ``Sequence[T]``.
    """

    items: Sequence[T]
    next_page_token: str | None
    total_size: int | None = None

    def as_body(self) -> dict[str, Any]:
        """Return the wire body, camelCase, omitting an absent ``totalSize``."""
        body: dict[str, Any] = {
            "items": list(self.items),
            "nextPageToken": self.next_page_token,
        }
        if self.total_size is not None:
            body["totalSize"] = self.total_size
        return body


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
