"""Django-specific utility helpers.

Provides:

- :class:`RequestUtils` — debug snapshot extraction from a Django
  :class:`~django.http.HttpRequest`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, cast

from django.http import HttpRequest

__all__ = [
    "RequestUtils",
]

_REDACTED_HEADERS = frozenset(
    {
        "HTTP_AUTHORIZATION",
        "HTTP_COOKIE",
        "HTTP_SET_COOKIE",
        "HTTP_X_API_KEY",
        "HTTP_X_AUTH_TOKEN",
    }
)


class _HttpHeadersProtocol(Protocol):
    def items(self) -> Iterable[tuple[object, object]]: ...


# ---------------------------------------------------------------------------
# RequestUtils
# ---------------------------------------------------------------------------


class RequestUtils:
    """Helpers for extracting diagnostic information from an HTTP request.

    All methods are static.
    """

    @staticmethod
    def debug_request(request: HttpRequest) -> dict[str, Any]:
        """Return a structured snapshot of *request* for logging or error reports.

        Collects path, method, content type, scheme, host/port, the full set of
        HTTP headers, and selected META entries.  No external calls are made.

        Works with both Django's :class:`~django.http.HttpRequest` and DRF's
        ``rest_framework.request.Request`` (which exposes the same interface).
        """
        meta = dict(cast(Mapping[str, object], cast(Any, request).META))
        headers = {
            str(key): str(value)
            for key, value in cast(
                _HttpHeadersProtocol, cast(Any, request).headers
            ).items()
        }
        return {
            "path": request.path,
            "path_info": request.path_info,
            "method": request.method,
            "content_type": cast(str | None, cast(Any, request).content_type),
            "scheme": request.scheme,
            "absolute_uri": cast(str, cast(Any, request).build_absolute_uri()),
            "full_path": request.get_full_path(),
            "host": request.get_host(),
            "port": request.get_port(),
            "headers": headers,
            "meta": {
                "REMOTE_ADDR": meta.get("REMOTE_ADDR"),
                "REMOTE_HOST": meta.get("REMOTE_HOST"),
                "SERVER_PORT": meta.get("SERVER_PORT"),
                "PATH_INFO": meta.get("PATH_INFO"),
                **{
                    k: ("<redacted>" if k in _REDACTED_HEADERS else str(v))
                    for k, v in meta.items()
                    if str(k).startswith("HTTP_")
                },
            },
        }
