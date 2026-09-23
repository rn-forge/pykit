"""Django wiring for the OWASP REST Security Cheat Sheet response headers.

Most of the preset is Django's own `SecurityMiddleware` and
`XFrameOptionsMiddleware`, configured through :data:`SECURITY_SETTINGS`. The
two headers Django has no built-in setting for — `Cache-Control` and the CSP
`frame-ancestors` directive — come from :class:`SecurityHeadersMiddleware`,
reading `rn_forge.web.security.API_SECURITY_HEADERS` (the `security` extra).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from rn_forge.web.security import API_SECURITY_HEADERS

__all__ = ["SECURITY_SETTINGS", "SecurityHeadersMiddleware"]

SECURITY_SETTINGS: Final[Mapping[str, Any]] = {
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "SECURE_REFERRER_POLICY": "no-referrer",
    "X_FRAME_OPTIONS": "DENY",
    "SECURE_HSTS_SECONDS": 0,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
}
"""Settings for Django's ``SecurityMiddleware`` and ``XFrameOptionsMiddleware``.

Spread into your settings module: ``globals().update(SECURITY_SETTINGS)``, or
assign the keys you want individually. HSTS is off (``SECURE_HSTS_SECONDS =
0``) by default, matching the FastAPI binding's ``hsts=False`` — a deployment
that terminates TLS itself overrides ``SECURE_HSTS_SECONDS`` (a year is
``31_536_000``) and ``SECURE_HSTS_INCLUDE_SUBDOMAINS``.
"""


class SecurityHeadersMiddleware:
    """Add ``Cache-Control`` and CSP ``frame-ancestors``: the headers Django has no setting for.

    Uses setdefault semantics: a view that already set either header keeps its
    own value. Place it anywhere in ``MIDDLEWARE``; order relative to
    ``SecurityMiddleware`` does not matter since the two never collide.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        """Run the middleware for one request."""
        response = self.get_response(request)
        for name in ("Cache-Control", "Content-Security-Policy"):
            if not response.has_header(name):
                response[name] = API_SECURITY_HEADERS[name]
        return response
