"""OIDC bearer authentication: discovery, token verification and the
authenticator that maps verified claims to a :class:`~rn_forge.auth.Principal`.

:class:`TokenVerificationError` carries the specific failure reason. Log it;
never send it to the client.

Requires the ``oidc`` extra. Not imported by :mod:`rn_forge.auth`; import this
module directly.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Self, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient
from rn_forge.auth.principal import Principal, principal_from_claims
from rn_forge.commons.exceptions import AppException
from rn_forge.web.auth import Credentials
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = [
    "FetchJson",
    "JwtVerifier",
    "OidcAuthenticator",
    "OidcConfiguration",
    "TokenVerificationError",
    "discover_oidc",
    "fetch_json",
]

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
    _require_secure_url(url)
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = cast(object, json.load(response))
    except (OSError, ValueError) as exc:
        raise TokenVerificationError("Could not fetch {}: {}", url, exc) from exc
    if not isinstance(body, Mapping):
        raise TokenVerificationError("Expected a JSON object from {}", url)
    return cast(Mapping[str, Any], body)


def _require_secure_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
    ):
        raise TokenVerificationError("Refusing to fetch key material over {}", url)


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


class JwtVerifier:
    """Verify a JWT against a key set, an issuer and an audience.

    ``exp``, ``iss`` and ``aud`` are required as well as checked: a token that
    simply omits ``exp`` would otherwise never expire. The algorithm allow-list
    is what rejects ``alg: none`` and an HMAC token signed with the public key.

    Args:
        jwks: Where signing keys come from. It caches the key set and refetches
            for an unknown ``kid`` at most once per its ``cooldown_duration``.
        issuer: The exact ``iss`` accepted.
        audience: The ``aud`` accepted — one value, or any of several.
        algorithms: The signature algorithms accepted.
        leeway: Seconds of clock skew tolerated on ``exp``/``nbf``/``iat``.
    """

    def __init__(
        self,
        *,
        jwks: PyJWKClient,
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
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier by OIDC discovery on *issuer*.

        Discovery runs once, here. Build the verifier at startup, not per request.

        Args:
            issuer: The IdP's issuer URL.
            audience: The ``aud`` accepted — one value, or any of several.
            fetch: The transport for the discovery document. The key set is
                fetched by :class:`jwt.PyJWKClient`.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.
                An unknown ``kid`` triggers a refetch only after this long.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
        """
        configuration = discover_oidc(issuer, fetch=fetch)
        return cls.from_jwks_url(
            configuration.jwks_uri,
            issuer=configuration.issuer,
            audience=audience,
            algorithms=algorithms,
            leeway=leeway,
            lifespan=lifespan,
            cooldown_duration=cooldown_duration,
        )

    @classmethod
    def from_jwks_url(
        cls,
        jwks_url: str,
        *,
        issuer: str,
        audience: str | Sequence[str],
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier from a known JWKS URL, skipping discovery.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            audience: The ``aud`` accepted — one value, or any of several.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.
                An unknown ``kid`` triggers a refetch only after this long.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
        """
        _require_secure_url(jwks_url)
        client = PyJWKClient(
            jwks_url,
            lifespan=lifespan,
            cooldown_duration=cooldown_duration,
            timeout=5.0,
        )
        return cls(
            jwks=client,
            issuer=issuer,
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


type ClaimsToPrincipal = Callable[[Mapping[str, Any]], Principal]


class OidcAuthenticator:
    """An :class:`~rn_forge.auth.Authenticator` backed by a :class:`JwtVerifier`.

    Build one at startup and reuse it: the verifier holds the JWKS cache, so a
    per-request instance refetches the key set on every call.

    The reason a token was rejected is carried on the raised
    :class:`~rn_forge.web.exceptions.AuthenticationFailed` for the binding to
    log. It never reaches the response body — both framework packages render a
    401 with :data:`~rn_forge.web.AUTH_FAILED_DETAIL`.

    Args:
        verifier: Verifies the bearer token and returns its claims.
        claims_to_principal: Verified claims → principal. Defaults to
            :func:`~rn_forge.auth.principal_from_claims`; override it for
            an IdP whose roles or scopes sit somewhere non-standard.
    """

    def __init__(
        self,
        verifier: JwtVerifier,
        *,
        claims_to_principal: ClaimsToPrincipal = principal_from_claims,
    ) -> None:
        self._verifier = verifier
        self._claims_to_principal = claims_to_principal

    @classmethod
    def from_issuer(
        cls,
        issuer: str,
        *,
        audience: str | Sequence[str],
        claims_to_principal: ClaimsToPrincipal = principal_from_claims,
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build an authenticator by OIDC discovery on *issuer*.

        Discovery runs once, here — so call this at startup, not per request.

        Args:
            issuer: The IdP's issuer URL. Its
                ``/.well-known/openid-configuration`` supplies the ``jwks_uri``.
            audience: The ``aud`` accepted — one value, or any of several.
            claims_to_principal: See the class docstring.
            fetch: The JSON transport for the discovery document.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
        """
        return cls(
            JwtVerifier.from_issuer(
                issuer,
                audience=audience,
                fetch=fetch,
                algorithms=algorithms,
                leeway=leeway,
                lifespan=lifespan,
                cooldown_duration=cooldown_duration,
            ),
            claims_to_principal=claims_to_principal,
        )

    @classmethod
    def from_jwks_url(
        cls,
        jwks_url: str,
        *,
        issuer: str,
        audience: str | Sequence[str],
        claims_to_principal: ClaimsToPrincipal = principal_from_claims,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build an authenticator from a known JWKS URL, skipping discovery.

        For an IdP that publishes no discovery document, or a deployment that
        pins the key-set URL.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            audience: The ``aud`` accepted — one value, or any of several.
            claims_to_principal: See the class docstring.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
        """
        return cls(
            JwtVerifier.from_jwks_url(
                jwks_url,
                issuer=issuer,
                audience=audience,
                algorithms=algorithms,
                leeway=leeway,
                lifespan=lifespan,
                cooldown_duration=cooldown_duration,
            ),
            claims_to_principal=claims_to_principal,
        )

    def authenticate(self, *, credentials: Credentials) -> Principal:
        """See :meth:`rn_forge.auth.Authenticator.authenticate`.

        Raises:
            AuthenticationFailed: The token failed verification, or *credentials*
                carry a scheme other than ``Bearer``.
        """
        if credentials.scheme.lower() != "bearer":
            raise AuthenticationFailed(
                "Unsupported scheme {}", credentials.scheme, error_code=401
            )
        try:
            claims = self._verifier.verify(credentials.token)
        except TokenVerificationError as exc:
            raise AuthenticationFailed(exc.message, error_code=401) from exc
        return self._claims_to_principal(claims)
