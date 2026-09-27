"""FastAPI dependencies for pagination and conditional request headers.

Factories keep endpoint-specific limits and header names in scope for FastAPI
without relying on closure variables in evaluated annotations.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from fastapi import Header, Query, Request
from fastapi.responses import Response

from rn_forge.web import (
    ANY_ETAG,
    DEFAULT_PAGE_SIZE_PARAM,
    DEFAULT_PAGE_TOKEN_PARAM,
    ORDER_BY_PARAM,
    Cursor,
    EntityVersionETagCodec,
    IDEMPOTENCY_KEY_HEADER,
    ETagCodec,
    OrderField,
    check_idempotency_key,
    check_precondition,
    clamp_page_size,
    decode_cursor,
    is_not_modified,
    parse_order_by,
)

__all__ = [
    "conditional_get",
    "order_by_param",
    "page_params",
    "require_idempotency_key",
    "require_if_match",
]


def page_params(*, cap: int, default: int) -> Callable[..., tuple[int, Cursor | None]]:
    """Return a dependency yielding ``(page_size, cursor)`` from ``pageSize``/``pageToken``.

    The size is **clamped, never rejected** (AIP-158), so the parameter carries
    no ``le=`` bound — that would be a 422 — and states the cap in its
    description instead. The token is decoded eagerly, so a tampered one is a
    400 before it reaches a query.

    Args:
        cap: The largest page this endpoint serves.
        default: The page size when the client asks for none.
    """

    def dependency(
        page_size: int | None = Query(
            default=None,
            alias=DEFAULT_PAGE_SIZE_PARAM,
            description=f"Requested page size. Above {cap} it is clamped to {cap}.",
        ),
        page_token: str | None = Query(
            default=None,
            alias=DEFAULT_PAGE_TOKEN_PARAM,
            description="The previous page's `nextPageToken`. Absent for the first page.",
        ),
    ) -> tuple[int, Cursor | None]:
        size = clamp_page_size(page_size, default=default, cap=cap)
        return size, decode_cursor(page_token) if page_token is not None else None

    return dependency


def order_by_param(
    *, allowed: Collection[str]
) -> Callable[..., tuple[OrderField, ...]]:
    """Return a dependency yielding the parsed AIP-132 ``orderBy`` terms.

    A term outside *allowed*, a malformed one, or more than one term is a 400 before it reaches a
    query. Pass the result and the decoded cursor to
    :func:`rn_forge.web.check_cursor_order`, and the canonical order from
    :func:`rn_forge.web.format_order_by` to :func:`rn_forge.web.encode_cursor`.

    Args:
        allowed: The field names the endpoint can sort by, as they appear on the wire.
    """
    names = sorted(allowed)

    def dependency(
        order_by: str | None = Query(
            default=None,
            alias=ORDER_BY_PARAM,
            description=(
                "Sort order: one field, e.g. `displayName desc`. "
                f"Sortable fields: {', '.join(names)}."
            ),
        ),
    ) -> tuple[OrderField, ...]:
        return parse_order_by(order_by, allowed=names)

    return dependency


def require_idempotency_key(
    *, header: str = IDEMPOTENCY_KEY_HEADER
) -> Callable[..., str]:
    """Return a dependency yielding the idempotency key, or raising a 400 without one.

    Args:
        header: The request header carrying the key.
    """

    def dependency(key: str | None = Header(default=None, alias=header)) -> str:
        return check_idempotency_key(key, header=header)

    return dependency


def conditional_get(request: Request, etag: str) -> Response | None:
    """Return the 304 to send for *request*'s ``If-None-Match``, or ``None``.

    Call once the resource's current ETag is known. ``None`` means the caller
    proceeds with its normal 200 response; a non-``None`` result is a
    :class:`~fastapi.responses.Response` to return as-is — 304, no body, the
    ``ETag`` repeated (RFC 9110 §13.1.2, §15.4.5).

    Args:
        request: The inbound request.
        etag: The resource's current ETag validator.
    """
    if is_not_modified(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers={"ETag": etag})
    return None


def require_if_match(*, codec: ETagCodec | None = None) -> Callable[..., str]:
    """Return a dependency yielding the raw ``If-Match`` value of a write.

    Absent → 428, unparseable → 400, both before the route runs. The value is
    returned verbatim for a later :func:`rn_forge.web.check_precondition` call.

    Args:
        codec: The validator format. Defaults to
            :class:`rn_forge.web.EntityVersionETagCodec`.
    """
    parser = codec if codec is not None else EntityVersionETagCodec()

    def dependency(
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> str:
        if if_match is None:
            # Web owns the 428 and its detail; with required=True this raises.
            check_precondition(None, current_version=0, required=True)
        assert if_match is not None
        if if_match.strip() != ANY_ETAG:
            parser.parse(if_match)
        return if_match

    return dependency
