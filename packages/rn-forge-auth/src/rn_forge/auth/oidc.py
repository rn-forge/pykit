"""OIDC token verification: discovery, one validation profile per kind of token
(access, ID and logout) and the authenticator that maps verified access-token
claims to a :class:`~rn_forge.auth.Principal`.

A token is accepted only by the profile used at its own place: the claims and
the ``typ`` header each profile requires exclude the others.

:class:`TokenVerificationError` carries the specific failure reason. Log it;
never send it to the client.

Requires the ``oidc`` extra. Not imported by :mod:`rn_forge.auth`; import this
module directly.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, Self, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import jwt
from authlib.oidc.core import CodeIDToken
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from joserfc import jwt as joserfc_jwt
from joserfc.errors import JoseError
from joserfc.jwk import import_key
from jwt import PyJWKClient
from rn_forge.auth.principal import Principal, principal_from_claims
from rn_forge.auth.stores import ReplayStore
from rn_forge.commons.exceptions import AppException
from rn_forge.web.auth import Credentials
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = [
    "FetchJson",
    "IdTokenVerifier",
    "JwtVerifier",
    "LogoutTokenVerifier",
    "OidcAuthenticator",
    "OidcConfiguration",
    "TokenMode",
    "TokenVerificationError",
    "discover_oidc",
    "fetch_json",
]

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
_RFC9068_TYPES = frozenset({"at+jwt", "application/at+jwt"})
_RFC9068_CLAIMS = ["iss", "exp", "aud", "sub", "client_id", "iat", "jti"]
_RFC7519_CLAIMS = ["iss", "exp", "aud"]

type TokenMode = Literal["rfc9068", "rfc7519"]
"""The access-token standard a provider issues: RFC 9068 JWT access tokens, or
plain RFC 7519 JWTs."""

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

    Per RFC 8414 §3.3, the document's ``issuer`` must equal the issuer it was
    fetched for; a mismatch is an error.

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


def _new_jwks_client(
    url: str, *, lifespan: float, cooldown_duration: float
) -> PyJWKClient:
    _require_secure_url(url)
    return PyJWKClient(
        url, lifespan=lifespan, cooldown_duration=cooldown_duration, timeout=5.0
    )


def _signing_key(
    jwks: PyJWKClient, token: str, algorithms: Sequence[str]
) -> tuple[Mapping[str, Any], jwt.PyJWK]:
    """The unverified header and the key it names, once ``alg`` is allowed."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise TokenVerificationError("Token header has no kid")
    if header.get("alg") not in algorithms:
        raise TokenVerificationError(
            "Token algorithm {} is not accepted", header.get("alg")
        )
    return header, jwks.get_signing_key(kid)


def _media_type(header: Mapping[str, Any]) -> str | None:
    typ = header.get("typ")
    return typ.lower() if isinstance(typ, str) else None


class JwtVerifier:
    """The access-token profile: verify a bearer JWT against a key set, an issuer
    and an audience.

    ``mode="rfc9068"`` accepts only RFC 9068 access tokens: a ``typ`` header of
    ``at+jwt`` or ``application/at+jwt`` (case-insensitive), and ``iss``,
    ``exp``, ``aud``, ``sub``, ``client_id``, ``iat`` and ``jti`` present.
    ``mode="rfc7519"`` accepts a ``typ`` of ``JWT`` (case-insensitive) or none,
    requires ``iss``, ``aud`` and ``exp``, and validates ``sub``, ``nbf`` and
    ``iat`` when present.

    In both modes a token carrying ``nonce`` or ``events`` (an ID token or a
    logout token) is rejected, ``iss`` must equal the configured issuer, and
    ``aud`` must contain one of the configured audiences. The algorithm
    allow-list is what rejects ``alg: none`` and an HMAC token signed with the
    public key.

    Args:
        jwks: Where signing keys come from. It caches the key set and refetches
            for an unknown ``kid`` at most once per its ``cooldown_duration``.
        issuer: The exact ``iss`` accepted.
        audience: The ``aud`` accepted — one value, or any of several.
        algorithms: The signature algorithms accepted.
        leeway: Seconds of clock skew tolerated on ``exp``/``nbf``/``iat``.
        mode: The access-token standard the provider issues.
        login_client_id: The OIDC login client ID of this application, if any.

    Raises:
        ValueError: *login_client_id* is one of the accepted audiences and
            *mode* is not ``"rfc9068"``.
    """

    def __init__(
        self,
        *,
        jwks: PyJWKClient,
        issuer: str,
        audience: str | Sequence[str],
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        mode: TokenMode = "rfc7519",
        login_client_id: str | None = None,
    ) -> None:
        audiences = [audience] if isinstance(audience, str) else list(audience)
        if login_client_id in audiences and mode != "rfc9068":
            raise ValueError(
                f"The audience {login_client_id!r} is the OIDC login client ID; "
                "that is allowed only in rfc9068 mode"
            )
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience if isinstance(audience, str) else audiences
        self._algorithms = list(algorithms)
        self._leeway = leeway
        self._mode: TokenMode = mode

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
        mode: TokenMode = "rfc7519",
        login_client_id: str | None = None,
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
            mode: The access-token standard the provider issues.
            login_client_id: The OIDC login client ID of this application.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
            ValueError: See the class docstring.
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
            mode=mode,
            login_client_id=login_client_id,
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
        mode: TokenMode = "rfc7519",
        login_client_id: str | None = None,
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
            mode: The access-token standard the provider issues.
            login_client_id: The OIDC login client ID of this application.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
            ValueError: See the class docstring.
        """
        return cls(
            jwks=_new_jwks_client(
                jwks_url, lifespan=lifespan, cooldown_duration=cooldown_duration
            ),
            issuer=issuer,
            audience=audience,
            algorithms=algorithms,
            leeway=leeway,
            mode=mode,
            login_client_id=login_client_id,
        )

    def verify(self, token: str) -> Mapping[str, Any]:
        """Return *token*'s claims once it satisfies the access-token profile.

        Raises:
            TokenVerificationError: For any failure; the message says which.
        """
        try:
            header, key = _signing_key(self._jwks, token, self._algorithms)
            self._check_type(header)
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={
                    "require": _RFC9068_CLAIMS
                    if self._mode == "rfc9068"
                    else _RFC7519_CLAIMS
                },
            )
        except jwt.PyJWTError as exc:
            raise TokenVerificationError("Token verification failed: {}", exc) from exc
        for forbidden in ("nonce", "events"):
            if forbidden in claims:
                raise TokenVerificationError(
                    "Token carries {}, which an access token does not", forbidden
                )
        return claims

    def _check_type(self, header: Mapping[str, Any]) -> None:
        typ = _media_type(header)
        if self._mode == "rfc9068":
            if typ not in _RFC9068_TYPES:
                raise TokenVerificationError(
                    "Token typ {} is not an RFC 9068 access token", header.get("typ")
                )
        elif typ not in (None, "jwt"):
            raise TokenVerificationError(
                "Token typ {} is not accepted", header.get("typ")
            )


class IdTokenVerifier:
    """The ID-token profile: verify an ID token at the OIDC callback.

    Authlib's ``CodeIDToken`` checks ``iss``, ``aud``, ``azp``, ``exp``,
    ``iat``, ``nonce`` and ``at_hash``. Added here: the algorithm allow-list,
    a mandatory non-empty nonce, and ``auth_time`` within *max_age*.

    Args:
        jwks: Where signing keys come from.
        issuer: The exact ``iss`` accepted.
        client_id: The OIDC login client ID; the ``aud`` and ``azp`` expected.
        algorithms: The signature algorithms accepted.
        leeway: Seconds of clock skew tolerated.
        max_age: When set, the most seconds that may separate the token's
            ``auth_time`` from now; ``auth_time`` is then required.
    """

    def __init__(
        self,
        *,
        jwks: PyJWKClient,
        issuer: str,
        client_id: str,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age: int | None = None,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._client_id = client_id
        self._algorithms = list(algorithms)
        self._leeway = leeway
        self._max_age = max_age

    @classmethod
    def from_issuer(
        cls,
        issuer: str,
        *,
        client_id: str,
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age: int | None = None,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier by OIDC discovery on *issuer*.

        Args:
            issuer: The IdP's issuer URL.
            client_id: The OIDC login client ID.
            fetch: The transport for the discovery document.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age: See the class docstring.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
        """
        configuration = discover_oidc(issuer, fetch=fetch)
        return cls.from_jwks_url(
            configuration.jwks_uri,
            issuer=configuration.issuer,
            client_id=client_id,
            algorithms=algorithms,
            leeway=leeway,
            max_age=max_age,
            lifespan=lifespan,
            cooldown_duration=cooldown_duration,
        )

    @classmethod
    def from_jwks_url(
        cls,
        jwks_url: str,
        *,
        issuer: str,
        client_id: str,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age: int | None = None,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier from a known JWKS URL, skipping discovery.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            client_id: The OIDC login client ID.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age: See the class docstring.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
        """
        return cls(
            jwks=_new_jwks_client(
                jwks_url, lifespan=lifespan, cooldown_duration=cooldown_duration
            ),
            issuer=issuer,
            client_id=client_id,
            algorithms=algorithms,
            leeway=leeway,
            max_age=max_age,
        )

    def verify(
        self, token: str, *, nonce: str, access_token: str | None = None
    ) -> Mapping[str, Any]:
        """Return *token*'s claims once it satisfies the ID-token profile.

        Args:
            token: The ID token.
            nonce: The nonce sent in the authorization request. Must be non-empty.
            access_token: The access token returned with the ID token. When
                given and the ID token has ``at_hash``, the hash must match.

        Raises:
            TokenVerificationError: For any failure; the message says which.
        """
        if not nonce:
            raise TokenVerificationError("An ID token needs the expected nonce")
        try:
            _, key = _signing_key(self._jwks, token, self._algorithms)
            # joserfc takes key material, not a cryptography key object; an
            # HMAC key has no public_bytes and fails as AttributeError below.
            pem = key.key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
            decoded = joserfc_jwt.decode(
                token,
                import_key(pem, cast(Literal["RSA", "EC", "OKP"], key.key_type)),
                algorithms=self._algorithms,
            )
            claims = CodeIDToken(
                decoded.claims,
                decoded.header,
                options={
                    "iss": {"essential": True, "value": self._issuer},
                    "aud": {"essential": True, "value": self._client_id},
                    "exp": {"essential": True},
                    "iat": {"essential": True},
                },
                params={
                    "nonce": nonce,
                    "client_id": self._client_id,
                    "access_token": access_token,
                    "max_age": self._max_age,
                },
            )
            claims.validate(leeway=math.ceil(self._leeway))
        except (jwt.PyJWTError, JoseError, AttributeError) as exc:
            raise TokenVerificationError(
                "ID token verification failed: {}", exc
            ) from exc
        self._check_auth_time(claims)
        return dict(claims)

    def _check_auth_time(self, claims: Mapping[str, Any]) -> None:
        if self._max_age is None:
            return
        auth_time = cast(Any, claims.get("auth_time"))
        now = time.time()
        if not isinstance(auth_time, int | float) or isinstance(auth_time, bool):
            raise TokenVerificationError("ID token has no auth_time")
        if auth_time > now + self._leeway:
            raise TokenVerificationError("ID token auth_time is in the future")
        if now - auth_time > self._max_age + self._leeway:
            raise TokenVerificationError(
                "ID token auth_time is older than max_age {}", self._max_age
            )


class LogoutTokenVerifier:
    """The logout-token profile: verify an OIDC Back-Channel Logout token.

    Back-Channel Logout 1.0 §2.6 requires ``iss``, ``aud``, ``iat``, ``exp``,
    ``jti`` and ``events``; ``events`` must be an object whose
    ``http://schemas.openid.net/event/backchannel-logout`` member is an object;
    ``sid`` or ``sub`` must be present; ``nonce`` must be absent. Added here:
    the ``typ`` header is ``logout+jwt`` (optionally prefixed
    ``application/``, case-insensitive) or absent; ``iat`` is at most
    *max_age_seconds* old; and a ``jti`` is accepted once. The ``jti`` is
    recorded in *replay_store* under ``"{iss}|{jti}"`` until the token's ``exp``
    (at least one second), after every other check has passed.

    Args:
        jwks: Where signing keys come from.
        issuer: The exact ``iss`` accepted.
        client_id: The OIDC login client ID; the ``aud`` expected.
        replay_store: Remembers the ``jti`` values already accepted.
        algorithms: The signature algorithms accepted.
        leeway: Seconds of clock skew tolerated.
        max_age_seconds: The oldest ``iat``, in seconds, accepted.
    """

    def __init__(
        self,
        *,
        jwks: PyJWKClient,
        issuer: str,
        client_id: str,
        replay_store: ReplayStore,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age_seconds: float = 120.0,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._client_id = client_id
        self._replay_store = replay_store
        self._algorithms = list(algorithms)
        self._leeway = leeway
        self._max_age_seconds = max_age_seconds

    @classmethod
    def from_issuer(
        cls,
        issuer: str,
        *,
        client_id: str,
        replay_store: ReplayStore,
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age_seconds: float = 120.0,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier by OIDC discovery on *issuer*.

        Args:
            issuer: The IdP's issuer URL.
            client_id: The OIDC login client ID.
            replay_store: Remembers the ``jti`` values already accepted.
            fetch: The transport for the discovery document.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age_seconds: The oldest ``iat``, in seconds, accepted.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
        """
        configuration = discover_oidc(issuer, fetch=fetch)
        return cls.from_jwks_url(
            configuration.jwks_uri,
            issuer=configuration.issuer,
            client_id=client_id,
            replay_store=replay_store,
            algorithms=algorithms,
            leeway=leeway,
            max_age_seconds=max_age_seconds,
            lifespan=lifespan,
            cooldown_duration=cooldown_duration,
        )

    @classmethod
    def from_jwks_url(
        cls,
        jwks_url: str,
        *,
        issuer: str,
        client_id: str,
        replay_store: ReplayStore,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age_seconds: float = 120.0,
        lifespan: float = 300.0,
        cooldown_duration: float = 30.0,
    ) -> Self:
        """Build a verifier from a known JWKS URL, skipping discovery.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            client_id: The OIDC login client ID.
            replay_store: Remembers the ``jti`` values already accepted.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age_seconds: The oldest ``iat``, in seconds, accepted.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
        """
        return cls(
            jwks=_new_jwks_client(
                jwks_url, lifespan=lifespan, cooldown_duration=cooldown_duration
            ),
            issuer=issuer,
            client_id=client_id,
            replay_store=replay_store,
            algorithms=algorithms,
            leeway=leeway,
            max_age_seconds=max_age_seconds,
        )

    def verify(self, token: str) -> Mapping[str, Any]:
        """Return *token*'s claims once it satisfies the logout-token profile.

        Raises:
            TokenVerificationError: For any failure, including a ``jti`` already
                accepted; the message says which.
        """
        try:
            header, key = _signing_key(self._jwks, token, self._algorithms)
            typ = _media_type(header)
            if typ is not None and typ.removeprefix("application/") != "logout+jwt":
                raise TokenVerificationError(
                    "Token typ {} is not a logout token", header.get("typ")
                )
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=self._algorithms,
                audience=self._client_id,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["iss", "aud", "iat", "exp", "jti", "events"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(
                "Logout token verification failed: {}", exc
            ) from exc
        self._check_claims(claims)
        ttl = timedelta(seconds=max(1.0, claims["exp"] - time.time()))
        if not self._replay_store.record_once(
            f"{self._issuer}|{claims['jti']}", ttl=ttl
        ):
            raise TokenVerificationError(
                "Logout token {} was already used", claims["jti"]
            )
        return claims

    def _check_claims(self, claims: Mapping[str, Any]) -> None:
        events = cast(object, claims["events"])
        if not isinstance(events, Mapping) or not isinstance(
            cast(Mapping[str, Any], events).get(_BACKCHANNEL_LOGOUT_EVENT), Mapping
        ):
            raise TokenVerificationError(
                "Logout token has no back-channel logout event"
            )
        if "nonce" in claims:
            raise TokenVerificationError("Logout token carries a nonce")
        if not (claims.get("sid") or claims.get("sub")):
            raise TokenVerificationError("Logout token has neither sid nor sub")
        iat = claims["iat"]
        if (
            not isinstance(iat, int | float)
            or time.time() - iat > self._max_age_seconds
        ):
            raise TokenVerificationError(
                "Logout token was issued more than {} seconds ago",
                self._max_age_seconds,
            )


type ClaimsToPrincipal = Callable[[Mapping[str, Any]], Principal]


class OidcAuthenticator:
    """An :class:`~rn_forge.auth.Authenticator` backed by a :class:`JwtVerifier`.

    The verifier holds the JWKS cache; build one authenticator and reuse it.

    The reason a token was rejected is carried on the raised
    :class:`~rn_forge.web.exceptions.AuthenticationFailed`, for logging. It is
    not part of the 401 response body, which is
    :data:`~rn_forge.web.AUTH_FAILED_DETAIL`.

    Args:
        verifier: Verifies the bearer token and returns its claims.
        claims_to_principal: Verified claims → principal. Defaults to
            :func:`~rn_forge.auth.principal_from_claims`.
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
        mode: TokenMode = "rfc7519",
        login_client_id: str | None = None,
    ) -> Self:
        """Build an authenticator by OIDC discovery on *issuer*.

        Discovery runs once, here.

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
            mode: See :class:`JwtVerifier`.
            login_client_id: See :class:`JwtVerifier`.

        Raises:
            TokenVerificationError: Discovery failed, returned no ``jwks_uri``,
                or the ``jwks_uri`` is not HTTPS (or HTTP to a local host).
            ValueError: See :class:`JwtVerifier`.
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
                mode=mode,
                login_client_id=login_client_id,
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
        mode: TokenMode = "rfc7519",
        login_client_id: str | None = None,
    ) -> Self:
        """Build an authenticator from a known JWKS URL, skipping discovery.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            audience: The ``aud`` accepted — one value, or any of several.
            claims_to_principal: See the class docstring.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            lifespan: Seconds a fetched key set stays cached.
            cooldown_duration: The fewest seconds between two key set fetches.
            mode: See :class:`JwtVerifier`.
            login_client_id: See :class:`JwtVerifier`.

        Raises:
            TokenVerificationError: *jwks_url* is not HTTPS (or HTTP to a local
                host).
            ValueError: See :class:`JwtVerifier`.
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
                mode=mode,
                login_client_id=login_client_id,
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
