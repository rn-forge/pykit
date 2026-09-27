"""Token verification: JWKS key sets, JWT validation and OIDC discovery.

Verification only. This module turns a bearer token into **verified claims** and
nothing more: no HTTP-server concept, no ``Principal``. What a caller sees when
verification fails, and how claims become a principal, are ``rn-forge-web``'s
(commons cannot depend on web); a framework binding joins the two.

Provides:

- :func:`fetch_json` — the default transport: a small ``urllib`` GET, HTTPS only
  (plain HTTP is accepted for ``localhost``, for a local IdP in development).
- :func:`discover_oidc` — OIDC Discovery 1.0 / RFC 8414: read
  ``/.well-known/openid-configuration`` and return the issuer and ``jwks_uri``.
- :class:`JwksCache` — a JWKS (RFC 7517) fetched on demand, cached for
  ``max_age`` seconds, and refetched **once** on an unknown ``kid`` so a key
  rotation is picked up — bounded by ``min_refresh_interval`` so a flood of
  tokens with a bogus ``kid`` cannot hammer the IdP.
- :class:`JwtVerifier` — RFC 7519 validation: signature, ``exp``, ``aud``,
  ``iss``, and an algorithm allow-list, via PyJWT.
- :class:`TokenVerificationError` — every failure, carrying the specific reason
  in its message. **Log that reason; never send it to the client.**

The IdP is always configuration, never a constant here: Entra ID, Auth0, Okta
and Keycloak all work through the same two URLs.

Requires the ``auth`` extra (``pyjwt[crypto]``). Not imported by
``rn_forge.commons``'s curated ``__init__.py``; import this module directly.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Self, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWK, PyJWKSet

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = [
    "FetchJson",
    "JwksCache",
    "JwtVerifier",
    "OidcConfiguration",
    "TokenVerificationError",
    "discover_oidc",
    "fetch_json",
]

_LOGGER = AppLogger.get_logger(__name__)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

type FetchJson = Callable[[str], Mapping[str, Any]]
"""A transport: GET a URL and return the decoded JSON object."""


class TokenVerificationError(AppException):
    """A token, a key set or a discovery document failed verification.

    The message says why. It is for logs: a 401 body must not repeat it.
    """


def fetch_json(url: str, *, timeout: float = 5.0) -> Mapping[str, Any]:
    """GET *url* and return its JSON object body.

    Raises:
        TokenVerificationError: The URL is not HTTPS (or HTTP to a local host),
            the request fails, or the body is not a JSON object.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
    ):
        raise TokenVerificationError("Refusing to fetch key material over {}", url)
    request = Request(url, headers={"Accept": "application/json"})  # noqa: S310 - scheme checked above
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
            body = cast(object, json.load(response))
    except (OSError, ValueError) as exc:
        raise TokenVerificationError("Could not fetch {}: {}", url, exc) from exc
    if not isinstance(body, Mapping):
        raise TokenVerificationError("Expected a JSON object from {}", url)
    return cast(Mapping[str, Any], body)


@dataclass(frozen=True)
class OidcConfiguration:
    """The two members of an OIDC discovery document verification needs."""

    issuer: str
    jwks_uri: str


def discover_oidc(issuer: str, *, fetch: FetchJson = fetch_json) -> OidcConfiguration:
    """Read *issuer*'s ``/.well-known/openid-configuration``.

    RFC 8414 §3.3: the document's ``issuer`` must be the issuer it was fetched
    for. A mismatch is an error, not a warning — accepting it lets one tenant's
    configuration vouch for another's tokens.

    Raises:
        TokenVerificationError: The document is unreachable, lacks ``issuer`` or
            ``jwks_uri``, or names a different issuer.
    """
    base = issuer.rstrip("/")
    document = fetch(f"{base}/.well-known/openid-configuration")
    found_issuer, jwks_uri = document.get("issuer"), document.get("jwks_uri")
    if not isinstance(found_issuer, str) or not isinstance(jwks_uri, str):
        raise TokenVerificationError("Discovery document for {} is incomplete", issuer)
    if found_issuer.rstrip("/") != base:
        raise TokenVerificationError(
            "Discovery document issuer {} does not match {}", found_issuer, issuer
        )
    return OidcConfiguration(issuer=found_issuer, jwks_uri=jwks_uri)


class JwksCache:
    """A JSON Web Key Set, fetched lazily and refreshed on age or key rotation.

    Thread-safe: a sync web server verifies tokens on many threads at once.
    Held per process; an application keeps one instance per IdP.

    Args:
        jwks_url: The key set URL — a discovery document's ``jwks_uri``.
        fetch: The transport. Defaults to :func:`fetch_json`.
        max_age: Seconds a fetched key set is trusted before it is refetched.
        min_refresh_interval: The fewest seconds between two fetches triggered
            by an unknown ``kid``. This is the bound on how hard a stream of
            forged tokens can make this process call the IdP.
        clock: A monotonic clock, injectable for tests.
    """

    def __init__(
        self,
        jwks_url: str,
        *,
        fetch: FetchJson = fetch_json,
        max_age: float = 86_400.0,
        min_refresh_interval: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.jwks_url = jwks_url
        self._fetch = fetch
        self._max_age = max_age
        self._min_refresh_interval = min_refresh_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, PyJWK] | None = None
        self._fetched_at = 0.0

    def get_signing_key(self, kid: str) -> PyJWK:
        """Return the key with id *kid*, refetching the set when that could help.

        Raises:
            TokenVerificationError: No key has that id after the permitted
                refetch, or the key set cannot be fetched or parsed.
        """
        with self._lock:
            now = self._clock()
            if self._keys is None or now - self._fetched_at >= self._max_age:
                self._refresh(now)
            key = self._current_keys().get(kid)
            if key is None and now - self._fetched_at >= self._min_refresh_interval:
                _LOGGER.debug(
                    "Unknown kid, refetching JWKS: kid={} url={}", kid, self.jwks_url
                )
                self._refresh(now)
                key = self._current_keys().get(kid)
        if key is None:
            raise TokenVerificationError("No signing key with kid {}", kid)
        return key

    def _current_keys(self) -> dict[str, PyJWK]:
        return self._keys if self._keys is not None else {}

    def _refresh(self, now: float) -> None:
        document = self._fetch(self.jwks_url)
        try:
            key_set = PyJWKSet.from_dict(dict(document))
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(
                "Unusable JWKS at {}: {}", self.jwks_url, exc
            ) from exc
        self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
        self._fetched_at = now


class JwtVerifier:
    """Verify a JWT against a key set, an issuer and an audience.

    ``exp``, ``iss`` and ``aud`` are required as well as checked: a token that
    simply omits ``exp`` would otherwise never expire. The algorithm allow-list
    is what rejects ``alg: none`` and an HMAC token signed with the public key.

    Args:
        jwks: Where signing keys come from.
        issuer: The exact ``iss`` accepted.
        audience: The ``aud`` accepted — one value, or any of several.
        algorithms: The signature algorithms accepted.
        leeway: Seconds of clock skew tolerated on ``exp``/``nbf``/``iat``.
    """

    def __init__(
        self,
        *,
        jwks: JwksCache,
        issuer: str,
        audience: str | Sequence[str],
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience if isinstance(audience, str) else list(audience)
        self._algorithms = list(algorithms)
        self._leeway = leeway

    @classmethod
    def from_issuer(
        cls,
        issuer: str,
        *,
        audience: str | Sequence[str],
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age: float = 86_400.0,
    ) -> Self:
        """Build a verifier by OIDC discovery on *issuer*.

        Discovery runs once, here. Build the verifier at startup, not per request.
        """
        configuration = discover_oidc(issuer, fetch=fetch)
        return cls(
            jwks=JwksCache(configuration.jwks_uri, fetch=fetch, max_age=max_age),
            issuer=configuration.issuer,
            audience=audience,
            algorithms=algorithms,
            leeway=leeway,
        )

    def verify(self, token: str) -> Mapping[str, Any]:
        """Return *token*'s claims once its signature and registered claims check out.

        Raises:
            TokenVerificationError: For any failure; the message says which.
        """
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str):
                raise TokenVerificationError("Token header has no kid")
            if header.get("alg") not in self._algorithms:
                raise TokenVerificationError(
                    "Token algorithm {} is not accepted", header.get("alg")
                )
            key = self._jwks.get_signing_key(kid)
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenVerificationError("Token verification failed: {}", exc) from exc
        return claims
