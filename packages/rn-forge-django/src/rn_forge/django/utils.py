"""Request diagnostics and configuration guards for Django."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.runtime.environment import Environment

__all__ = [
    "RequestUtils",
    "require_environment",
    "require_settings",
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

        Sensitive authorization, cookie, and API-key metadata is redacted.
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


# ---------------------------------------------------------------------------
# Startup guards
# ---------------------------------------------------------------------------


def require_settings(*names: str) -> None:
    """Raise ``ImproperlyConfigured`` if any named Django setting is unset or blank.

    All missing names are reported together. Empty values follow
    :meth:`rn_forge.commons.lang.utils.AppUtils.is_empty`.

    Raises:
        ImproperlyConfigured: One or more settings are missing.
    """
    missing = sorted(
        name for name in names if AppUtils.is_empty(getattr(settings, name, None))
    )
    if missing:
        raise ImproperlyConfigured(
            f"Missing required Django setting(s): {', '.join(missing)}"
        )


def require_environment(*names: str) -> dict[str, str]:
    """Return the named environment variables, raising if any is unset or blank.

    Raises:
        ImproperlyConfigured: One or more variables are missing; the message
            names all of them.
    """
    try:
        return Environment.require(*names)
    except AppException as exc:
        raise ImproperlyConfigured(exc.message) from exc
