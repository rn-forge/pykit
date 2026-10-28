"""Synchronizer-token CSRF protection for the session-authenticated routes.

The token is a random value kept server-side under the session ID, and handed
to the browser in the readable ``XSRF-TOKEN`` cookie. :class:`CsrfProtection`
compares it in constant time with the ``X-XSRF-TOKEN`` header on an unsafe
request, which are the names Angular's ``HttpClient`` uses. Before sign-in the
record is keyed by an anonymous ID behind the ``__Host-session`` cookie, so the
login request is protected too. ``SessionMiddleware`` decides which requests
are checked: those that carry the session cookie, and the password-login path.

The request's ``Origin`` (``Referer`` over HTTPS when there is no ``Origin``)
must be its own origin or one of ``trusted_origins``, and
``Sec-Fetch-Site: cross-site`` is rejected. The request's own scheme and host
come from ``X-Forwarded-Proto`` and ``X-Forwarded-Host`` only when the peer is
one of ``trusted_proxies``. A request with a ``Bearer`` ``Authorization`` header
skips the check.
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import threading
from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol, runtime_checkable
from urllib.parse import urlsplit

from fastapi import Response
from rn_forge.web import CsrfFailed, ProblemRegistry, default_registry

__all__ = [
    "ANONYMOUS_PREFIX",
    "ANONYMOUS_TTL",
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "CsrfProtection",
    "CsrfStore",
    "InMemoryCsrfStore",
]

CSRF_COOKIE: Final = "XSRF-TOKEN"
"""The readable cookie that carries the token."""

CSRF_HEADER: Final = "X-XSRF-TOKEN"
"""The request header that must repeat the token."""

ANONYMOUS_PREFIX: Final = "anon."
"""Starts the ID of an anonymous session; ``.`` is not in a session store's IDs."""

ANONYMOUS_TTL: Final = timedelta(minutes=10)
"""How long an anonymous session holds its token."""

_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@runtime_checkable
class CsrfStore(Protocol):
    """Holds the CSRF token of each session, keyed by session ID.

    Every method is synchronous and thread-safe.
    """

    def save(self, key: str, token: str, *, ttl: timedelta) -> None:
        """Store *token* under *key*, replacing any token, for *ttl*."""
        ...

    def get(self, key: str) -> str | None:
        """Return the token stored under *key*, or ``None`` when there is none."""
        ...

    def delete(self, key: str) -> None:
        """Remove the token stored under *key*, if any."""
        ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryCsrfStore:
    """:class:`CsrfStore` held in process memory, for tests and development.

    Args:
        clock: Returns the current time, aware.
    """

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._tokens: dict[str, tuple[str, datetime]] = {}
        self._lock = threading.Lock()

    def save(self, key: str, token: str, *, ttl: timedelta) -> None:
        """Store *token* under *key* for *ttl*."""
        with self._lock:
            self._tokens[key] = (token, self._clock() + ttl)

    def get(self, key: str) -> str | None:
        """Return the unexpired token under *key*."""
        with self._lock:
            held = self._tokens.get(key)
            if held is None:
                return None
            if held[1] <= self._clock():
                del self._tokens[key]
                return None
            return held[0]

    def delete(self, key: str) -> None:
        """Remove the token under *key*."""
        with self._lock:
            self._tokens.pop(key, None)


def _origin(value: str) -> str:
    return value.rstrip("/").lower()


def _first(value: str | None) -> str | None:
    if value is None:
        return None
    return value.partition(",")[0].strip() or None


class CsrfProtection:
    """The token store and the checks that guard unsafe requests.

    Args:
        store: Holds the tokens.
        problem_type_base: Prefix of the ``type`` URI of the ``csrf-failed``
            problem; empty for ``about:blank``.
        trusted_origins: Origins, besides the request's own, that may send an
            unsafe request, such as ``https://app.example``.
        trusted_proxies: Peer addresses or CIDR networks whose forwarded scheme
            and host headers are believed.
    """

    def __init__(
        self,
        *,
        store: CsrfStore,
        problem_type_base: str,
        trusted_origins: Collection[str] = (),
        trusted_proxies: Collection[str] = (),
    ) -> None:
        self.store = store
        self.registry: ProblemRegistry = default_registry(type_base=problem_type_base)
        self._origins = frozenset(_origin(origin) for origin in trusted_origins)
        self._proxies = tuple(
            ipaddress.ip_network(proxy, strict=False) for proxy in trusted_proxies
        )

    @staticmethod
    def is_anonymous(key: str | None) -> bool:
        """Whether *key* has the shape of an anonymous session ID."""
        return key is not None and key.startswith(ANONYMOUS_PREFIX)

    @staticmethod
    def new_anonymous_id() -> str:
        """A new anonymous session ID."""
        return ANONYMOUS_PREFIX + secrets.token_urlsafe(32)

    def mint(self, key: str, *, ttl: timedelta) -> str:
        """Store a new random token under *key*, replacing any token, and return it."""
        token = secrets.token_urlsafe(32)
        self.store.save(key, token, ttl=ttl)
        return token

    @staticmethod
    def set_cookie(response: Response, token: str) -> None:
        """Set the token cookie on *response*."""
        response.set_cookie(
            CSRF_COOKIE,
            token,
            secure=True,
            httponly=False,
            samesite="lax",
            path="/",
        )

    def check(
        self,
        *,
        method: str,
        headers: Mapping[str, str],
        scheme: str,
        peer: str | None,
        expected: str | None,
    ) -> None:
        """Check one request.

        Args:
            method: The HTTP method.
            headers: The request headers, by lowercase name.
            scheme: The scheme the server received the request on.
            peer: The address of the connection's peer.
            expected: The token stored for the request's session, or ``None``
                when it has none.

        Raises:
            CsrfFailed: The request is unsafe and the origin, fetch-metadata
                or token check fails.
        """
        if method in _SAFE_METHODS:
            return
        authorization = headers.get("authorization", "")
        if authorization.partition(" ")[0].lower() == "bearer":
            return
        if headers.get("sec-fetch-site") == "cross-site":
            raise CsrfFailed("Sec-Fetch-Site is cross-site")
        self._check_origin(headers, scheme, peer)
        supplied = headers.get(CSRF_HEADER.lower())
        if not supplied or expected is None:
            raise CsrfFailed("CSRF token missing")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise CsrfFailed("CSRF token mismatch")

    def _check_origin(
        self, headers: Mapping[str, str], scheme: str, peer: str | None
    ) -> None:
        origin = headers.get("origin")
        own = self._own_origin(headers, scheme, peer)
        allowed = self._origins | {own}
        if origin is not None:
            if _origin(origin) not in allowed:
                raise CsrfFailed("Origin checking failed")
            return
        if own.startswith("https://"):
            referer = headers.get("referer")
            parts = urlsplit(referer) if referer else None
            if parts is None or parts.scheme != "https" or not parts.netloc:
                raise CsrfFailed("Referer checking failed")
            if f"{parts.scheme}://{parts.netloc}".lower() not in allowed:
                raise CsrfFailed("Referer checking failed")

    def _own_origin(
        self, headers: Mapping[str, str], scheme: str, peer: str | None
    ) -> str:
        host = headers.get("host", "")
        if self._trusts(peer):
            scheme = _first(headers.get("x-forwarded-proto")) or scheme
            host = _first(headers.get("x-forwarded-host")) or host
        return f"{scheme}://{host}".lower()

    def _trusts(self, peer: str | None) -> bool:
        if peer is None:
            return False
        try:
            address = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(address in network for network in self._proxies)
