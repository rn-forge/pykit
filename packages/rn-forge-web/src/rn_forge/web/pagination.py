"""Cursor pagination: opaque tokens, in Google AIP-158's spelling.

There is no IETF standard for pagination. `AIP-158 <https://google.aip.dev/158>`_
is the de facto convention for modern REST APIs and the OpenAPI generators that
read them, and it is adopted here wholesale rather than inventing a spelling —
for one specific reason. AIP-158 says that a ``page_size`` above the maximum
"should coerce down to the maximum": **clamp, never reject**, which is exactly
what the surveyed implementation independently arrived at, and exactly what a
FastAPI ``Query(le=...)`` would violate. When a standard and an independent
implementation agree, the standard wins the naming.

The contract, normative for every framework package in this kit:

| Direction | JSON / query name | Python name | Meaning |
| --- | --- | --- | --- |
| request | `pageSize` | `page_size` | clamped server-side to the cap, never rejected |
| request | `pageToken` | `page_token` | opaque continuation token; absent means the first page |
| response | `nextPageToken` | `next_page_token` | opaque; absent or `null` means the last page |
| response | `items` | `items` | the page's elements |
| response | `totalSize` | `total_size` | **optional, off by default** |

Three notes that stop this drifting:

- **The token is opaque and a client must not parse it.** That is what lets the
  codec change without a client change, and it is why nothing is signed: a
  cursor is opaque, not secret, and signing means key management.
- **AIP-158 names the response array after the resource** (``users``,
  ``builds``). A library cannot, so this package fixes it at ``items`` and
  records the deviation. A generated client then has one page type rather than
  one per resource, which is the better trade for a shared kit.
- **``totalSize`` is off by default.** Page-number pagination gives a total for
  free and keyset does not; a UI that needs one opts in per endpoint and pays
  for the count.

Not here: the keyset SQL. Turning a :class:`Cursor` into
``WHERE (sort_key, id) > (?, ?)`` is ORM-specific.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote

from rn_forge.commons.lang.dataclasses import DataclassMixin
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
class Page[T](DataclassMixin):
    """One page of results, in the AIP-158 envelope.

    ``total_size`` is omitted from :meth:`as_body` when ``None`` rather than
    serialized as ``null``: a keyset query cannot cheaply count, and a ``null``
    total invites a client to render "of ?" where the field should simply not
    be there.
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

    AIP-158: an over-large ``pageSize`` coerces down to the maximum. Rejecting
    it is a 400 the client cannot act on beyond guessing the cap.

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
