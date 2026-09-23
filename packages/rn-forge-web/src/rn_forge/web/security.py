"""OWASP REST Security Cheat Sheet response headers, via the ``secure`` library.

**Requires the ``security`` extra.** Not re-exported from the package facade;
import it directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import secure

from rn_forge.web.asgi import ASGIApp, Message, Receive, Scope, Send

__all__ = ["API_SECURITY_HEADERS", "HSTS_HEADER", "SecurityHeadersMiddleware"]

_PRESET: Final = secure.Secure(
    cache=secure.CacheControl().no_store(),
    csp=secure.ContentSecurityPolicy().frame_ancestors("'none'"),
    xcto=secure.XContentTypeOptions(),
    xfo=secure.XFrameOptions().deny(),
    referrer=secure.ReferrerPolicy().no_referrer(),
)

API_SECURITY_HEADERS: Final[Mapping[str, str]] = dict(_PRESET.header_items())
"""The OWASP REST Security Cheat Sheet response headers, HSTS excluded.

``Strict-Transport-Security`` is HTTPS-deployment-specific and is each stack's
own opt-in flag rather than part of this preset.
"""

_HSTS_PRESET: Final = secure.Secure(
    hsts=secure.StrictTransportSecurity().max_age(31_536_000).include_subdomains()
)

HSTS_HEADER: Final[Mapping[str, str]] = dict(_HSTS_PRESET.header_items())
"""``Strict-Transport-Security``, a year, including subdomains.

Added only when a stack's ``hsts`` flag is set — an HTTP deployment that sent
it would be telling browsers to refuse a future plaintext connection.
"""


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware stamping :data:`API_SECURITY_HEADERS` on every response.

    Uses ``setdefault`` semantics: a header name the downstream application
    already set is left alone, so a route's own ``Cache-Control`` wins.

    Args:
        app: The downstream ASGI application.
        headers: The headers to set. Defaults to :data:`API_SECURITY_HEADERS`.
    """

    def __init__(
        self, app: ASGIApp, *, headers: Mapping[str, str] = API_SECURITY_HEADERS
    ) -> None:
        self.app = app
        self.headers = headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the middleware for one connection."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                _setdefault_headers(message, self.headers)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _existing_headers(raw: object) -> list[tuple[bytes, bytes]]:
    """Return *raw* as a well-formed list of ASGI header pairs, or an empty one."""
    existing: list[tuple[bytes, bytes]] = []
    if not isinstance(raw, list):
        return existing
    for entry in raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:  # pyright: ignore[reportUnknownArgumentType]
            continue
        key, value = entry  # pyright: ignore[reportUnknownVariableType]
        if isinstance(key, bytes) and isinstance(value, bytes):
            existing.append((key, value))
    return existing


def _setdefault_headers(message: Message, headers: Mapping[str, str]) -> None:
    """Append each header in *headers* to *message*, skipping names already present."""
    existing = _existing_headers(message.get("headers"))
    present = {key.lower() for key, _value in existing}
    for name, value in headers.items():
        wanted = name.lower().encode("latin-1")
        if wanted not in present:
            existing.append((name.encode("latin-1"), value.encode("latin-1")))
    message["headers"] = existing
