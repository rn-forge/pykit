"""A FastAPI dependency stamping RFC 9745/RFC 8594 deprecation headers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import Response

from rn_forge.web import deprecation_headers

__all__ = ["deprecated"]


def deprecated(
    *,
    deprecated_at: datetime,
    sunset: datetime | None = None,
    link: str | None = None,
) -> Callable[[Response], None]:
    """Return a dependency that stamps :func:`rn_forge.web.deprecation_headers` on the response.

    Pair it with the route's own ``deprecated=True`` so the OpenAPI document
    also marks the operation deprecated — this dependency only sets the wire
    headers.

    Example::

        @app.get(
            "/v1/orders",
            deprecated=True,
            dependencies=[Depends(deprecated(deprecated_at=SUNSET_ANNOUNCED))],
        )

    Args:
        deprecated_at: When the endpoint became deprecated.
        sunset: When the endpoint stops being served. Omitted when unscheduled.
        link: A URI for the deprecation notice.
    """

    def dependency(response: Response) -> None:
        response.headers.update(
            deprecation_headers(deprecated_at=deprecated_at, sunset=sunset, link=link)
        )

    return dependency
