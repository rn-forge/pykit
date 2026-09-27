"""A view decorator stamping RFC 9745/RFC 8594 deprecation headers."""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import datetime

from django.http.response import HttpResponseBase
from rn_forge.web import deprecation_headers

__all__ = ["deprecated"]


def deprecated[**P](
    *,
    deprecated_at: datetime,
    sunset: datetime | None = None,
    link: str | None = None,
) -> Callable[[Callable[P, HttpResponseBase]], Callable[P, HttpResponseBase]]:
    """Decorate a view so every response carries :func:`rn_forge.web.deprecation_headers`.

    Pair it with drf-spectacular's ``@extend_schema(deprecated=True)`` so the
    OpenAPI document also marks the operation deprecated — this decorator only
    sets the wire headers.

    Args:
        deprecated_at: When the endpoint became deprecated.
        sunset: When the endpoint stops being served. Omitted when unscheduled.
        link: A URI for the deprecation notice.

    Example::

        class OrdersView(APIView):
            @extend_schema(deprecated=True)
            @deprecated(deprecated_at=SUNSET_ANNOUNCED)
            def get(self, request): ...
    """
    headers = deprecation_headers(deprecated_at=deprecated_at, sunset=sunset, link=link)

    def decorate(view: Callable[P, HttpResponseBase]) -> Callable[P, HttpResponseBase]:
        @functools.wraps(view)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> HttpResponseBase:
            response = view(*args, **kwargs)
            for name, value in headers.items():
                response[name] = value
            return response

        return wrapper

    return decorate
