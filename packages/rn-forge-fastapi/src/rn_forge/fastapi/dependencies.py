"""Request dependencies: page parameters, ``Idempotency-Key`` and ``If-Match``.

Five to ten lines each. The value is not the line count; it is that every
application spells them the same way, and that the one easy mistake — a
``Query(le=...)`` on the page size — is made once, here, correctly.

Each is a **factory**, so the cap and the header names are per-application
arguments rather than module constants. Each raises a :mod:`rn_forge.web`
exception and lets :func:`rn_forge.fastapi.register_problem_handlers` render it.

Parameter defaults, not ``Annotated``
-------------------------------------

``Query(...)`` and ``Header(...)`` are passed as parameter *defaults*. Under
``from __future__ import annotations`` an annotation is a string that FastAPI
evaluates against the module's globals, and a factory's arguments — the cap,
the header name — are closure variables that evaluation cannot see. A default
is evaluated when the inner function is defined, where they are in scope.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, Query

from rn_forge.web import (
    ANY_ETAG,
    DEFAULT_PAGE_SIZE_PARAM,
    DEFAULT_PAGE_TOKEN_PARAM,
    Cursor,
    EntityVersionETagCodec,
    ETagCodec,
    IdempotencyKeyRequired,
    check_precondition,
    clamp_page_size,
    decode_cursor,
)

__all__ = ["page_params", "require_idempotency_key", "require_if_match"]


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


def require_idempotency_key(*, header: str = "Idempotency-Key") -> Callable[..., str]:
    """Return a dependency yielding the idempotency key, or raising a 400 without one.

    It reads the key and nothing more. Storing it is an
    :class:`rn_forge.web.AsyncIdempotencyStore` the application supplies.

    Args:
        header: The request header carrying the key.
    """

    def dependency(key: str | None = Header(default=None, alias=header)) -> str:
        if not key:
            raise IdempotencyKeyRequired("{} is required", header, error_code=400)
        return key

    return dependency


def require_if_match(*, codec: ETagCodec | None = None) -> Callable[..., str]:
    """Return a dependency yielding the raw ``If-Match`` value of a write.

    Absent → 428, unparseable → 400, both before the route runs. The value is
    returned verbatim because the version comparison needs the entity's current
    version, which only the route has: pass it to
    :func:`rn_forge.web.check_precondition`.

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
