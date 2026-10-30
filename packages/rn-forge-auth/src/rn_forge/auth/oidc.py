"""OIDC: discovery, the login provider, one validation profile per kind of token
(access, ID and logout) and the authenticator that maps verified access-token
claims to a :class:`~rn_forge.auth.Principal`.

:class:`OidcProvider` runs the authorization code flow with PKCE over Authlib's
``OAuth2Session`` and verifies the ID token with :class:`IdTokenVerifier`.

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
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Self, cast
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import jwt
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.requests_client import OAuth2Session
from authlib.oidc.core import CodeIDToken
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from joserfc import jwt as joserfc_jwt
from joserfc.errors import JoseError
from joserfc.jwk import import_key
from jwt import PyJWKClient
from rn_forge.auth.accounts import AccountResolver
from rn_forge.auth.flow import LoginFailed
from rn_forge.auth.identity import (
    ExternalIdentity,
    IdentityProvider,
    LoginRequest,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)
from rn_forge.auth.principal import Principal, principal_from_claims
from rn_forge.auth.stores import ReplayStore
from rn_forge.commons.exceptions import AppException
from rn_forge.web.auth import Credentials
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = [
    "BackchannelLogout",
    "ClaimMapper",
    "FetchJson",
    "IdTokenVerifier",
    "JwtVerifier",
    "LogoutRevocation",
    "LogoutTokenVerifier",
    "OAuth2Endpoints",
    "OidcAuthenticator",
    "OidcConfiguration",
    "OidcProvider",
    "TokenHook",
    "TokenMode",
    "TokenVerificationError",
    "UpstreamTokens",
    "default_claim_mapper",
    "discover_oidc",
    "fetch_json",
]

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# An event-type URI that names the event; it is never fetched.
_BACKCHANNEL_LOGOUT_EVENT = (
    "http://schemas.openid.net/event/backchannel-logout"  # NOSONAR(S5332)
)
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
    request = Request(url, headers={"Accept": "application/json"})  # noqa: S310  # scheme checked by _require_secure_url
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310  # scheme checked by _require_secure_url
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
    """The two members of an OIDC discovery document verification needs.

    Attributes:
        issuer: The document's ``issuer``.
        jwks_uri: Where the key set is served.
        metadata: The whole discovery document.
    """

    issuer: str
    jwks_uri: str
    metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])


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
    return OidcConfiguration(
        issuer=found_issuer, jwks_uri=jwks_uri, metadata=dict(document)
    )


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
    # Read unverified only to pick the signing key; the caller verifies with it.
    header = jwt.get_unverified_header(token)  # NOSONAR(S5659)
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


type ClaimMapper = Callable[[str, Mapping[str, Any]], ExternalIdentity]
"""Maps ``(provider ID, verified claims)`` to an identity.

The claims are the ID token's, completed by UserInfo for any claim the ID token
lacks. Raise :class:`~rn_forge.auth.LoginFailed` to refuse the login."""

_PROTOCOL_CLAIMS = frozenset(
    {"iss", "aud", "exp", "iat", "nbf", "jti", "nonce", "at_hash", "c_hash", "azp"}
)
_PROFILE_CLAIMS = frozenset(
    {
        "sub",
        "email",
        "email_verified",
        "name",
        "picture",
        "groups",
        "auth_time",
        "amr",
        "sid",
    }
)


def _optional_str(claims: Mapping[str, Any], name: str) -> str | None:
    value = claims.get(name)
    return value if isinstance(value, str) else None


def _string_set(claims: Mapping[str, Any], name: str) -> frozenset[str]:
    value = cast(Any, claims.get(name))
    if not isinstance(value, list):
        return frozenset()
    items = cast(list[Any], value)
    return frozenset(item for item in items if isinstance(item, str))


def default_claim_mapper(provider: str, claims: Mapping[str, Any]) -> ExternalIdentity:
    """Map standard OIDC claims to an :class:`~rn_forge.auth.ExternalIdentity`.

    ``sub``, ``email``, ``email_verified``, ``name``, ``picture``, ``groups``,
    ``auth_time`` and ``amr`` fill the fields of the same name, and ``sid``
    fills ``session_ref``. A claim of the wrong type is ignored. Every other
    claim except the token-protocol ones (``iss``, ``aud``, ``exp``, ``iat``,
    ``nbf``, ``jti``, ``nonce``, ``at_hash``, ``c_hash``, ``azp``) goes to
    ``attributes``.

    Raises:
        LoginFailed: ``sub`` or ``iss`` is missing.
    """
    subject, issuer = _optional_str(claims, "sub"), _optional_str(claims, "iss")
    if not subject or not issuer:
        raise LoginFailed("login_failed", "claims lack sub or iss")
    auth_time = cast(Any, claims.get("auth_time"))
    verified = claims.get("email_verified")
    return ExternalIdentity(
        provider=provider,
        issuer=issuer,
        subject=subject,
        email=_optional_str(claims, "email"),
        email_verified=verified is True,
        name=_optional_str(claims, "name"),
        picture=_optional_str(claims, "picture"),
        groups=_string_set(claims, "groups"),
        attributes={
            name: value
            for name, value in claims.items()
            if name not in _PROTOCOL_CLAIMS | _PROFILE_CLAIMS
        },
        auth_time=(
            datetime.fromtimestamp(auth_time, UTC)
            if isinstance(auth_time, int | float) and not isinstance(auth_time, bool)
            else None
        ),
        amr=_string_set(claims, "amr"),
        session_ref=_optional_str(claims, "sid"),
    )


@dataclass(frozen=True)
class UpstreamTokens:
    """The tokens the provider returned from the code exchange.

    Attributes:
        access_token: The access token.
        id_token: The verified ID token; ``None`` for an OAuth 2.0 provider.
        refresh_token: The refresh token, if issued.
        scope: The granted scope, if the provider reported it.
    """

    access_token: str = field(repr=False)
    id_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    scope: str | None = None


type TokenHook = Callable[[ExternalIdentity, UpstreamTokens], None]
"""Receives the identity and the upstream tokens of a successful login."""

type UserInfoMode = Literal["auto", "always", "never"]


@dataclass(frozen=True)
class OAuth2Endpoints:
    """The endpoints of an OAuth 2.0 provider that has no discovery document.

    Attributes:
        authorization: The authorization endpoint.
        token: The token endpoint.
        user: The endpoint that returns the signed-in user as a JSON object.
    """

    authorization: str
    token: str
    user: str


class OidcProvider(IdentityProvider[LoginRequest]):
    """An OIDC :class:`~rn_forge.auth.IdentityProvider`: authorization code flow
    with PKCE (S256), over Authlib's ``OAuth2Session``.

    The authorization request carries ``state``, a nonce, the PKCE challenge and
    ``max_age`` when set; all of them are recorded on the login transaction.
    The callback is accepted only when its ``state`` equals the transaction's,
    its ``iss`` (RFC 9207) names the issuer, the code exchange succeeds and the
    ID token satisfies :class:`IdTokenVerifier`. The upstream tokens are
    discarded unless *token_hook* is given.

    :meth:`oauth2` builds the provider for a server with no ID token: ``kind``
    is ``"oauth2"``, the request carries no nonce, and the identity comes from
    the user endpoint called with the access token.

    Args:
        id: The provider ID.
        issuer: The IdP's issuer URL; its discovery document is read on first
            use. For an OAuth 2.0 provider, the fixed ``issuer`` of its
            identities.
        client_id: The registered client.
        client_secret: The client's secret; ``None`` for a public client.
        redirect_uri: The registered callback URL.
        scopes: The requested scopes; OIDC requires ``openid``. Defaults to
            ``openid email profile``, or to none for an OAuth 2.0 provider.
        max_age: When set, the most seconds since the user authenticated; sent
            on the authorization request and enforced on the ID token.
        userinfo: ``"always"`` calls the UserInfo endpoint, ``"never"`` does
            not, and ``"auto"`` calls it when the ID token has no ``email``. The
            UserInfo ``sub`` must equal the ID token's.
        claim_mapper: Replaces :func:`default_claim_mapper`.
        token_hook: Called with the identity and the upstream tokens after a
            successful login.
        fetch: The transport for the discovery document.
        algorithms: The ID-token signature algorithms accepted.
        leeway: Seconds of clock skew tolerated.
        timeout: Seconds before a back-channel request fails.
        token_endpoint_auth_method: How the client authenticates at the token
            endpoint.
        rp_initiated_logout: Whether :meth:`logout_redirect` returns the
            provider's ``end_session_endpoint``. Ignored for an OAuth 2.0
            provider, which has none.
        endpoints: When given, makes an OAuth 2.0 provider; see :meth:`oauth2`.
        subject_field: The user-endpoint member that is the subject.
        response_issuer: The ``iss`` an OAuth 2.0 authorization response must
            carry; ``None`` skips the check.

    Attributes:
        id: The provider ID.
        kind: ``"oidc"``, or ``"oauth2"`` for an OAuth 2.0 provider.
    """

    kind: ProviderKind

    # One keyword argument per provider setting.
    def __init__(
        self,  # NOSONAR(S107)
        *,
        id: str,
        issuer: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        scopes: Sequence[str] | None = None,
        max_age: int | None = None,
        userinfo: UserInfoMode = "auto",
        claim_mapper: ClaimMapper = default_claim_mapper,
        token_hook: TokenHook | None = None,
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        timeout: float = 5.0,
        token_endpoint_auth_method: str = "client_secret_basic",  # noqa: S107  # identifier name, not a secret
        rp_initiated_logout: bool = False,
        endpoints: OAuth2Endpoints | None = None,
        subject_field: str = "sub",
        response_issuer: str | None = None,
    ) -> None:
        if scopes is None:
            scopes = () if endpoints else ("openid", "email", "profile")
        if endpoints is None and "openid" not in scopes:
            raise ValueError("scopes must include openid")
        self.id = id
        self.kind = "oidc" if endpoints is None else "oauth2"
        self._issuer = issuer
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = list(scopes)
        self._max_age = max_age
        self._userinfo = userinfo
        self._claim_mapper = claim_mapper
        self._token_hook = token_hook
        self._fetch = fetch
        self._algorithms = list(algorithms)
        self._leeway = leeway
        self._timeout = timeout
        self._auth_method = (
            token_endpoint_auth_method if client_secret is not None else "none"
        )
        self._rp_initiated_logout = rp_initiated_logout
        self._endpoints = endpoints
        self._subject_field = subject_field
        self._response_issuer = response_issuer
        self._discovered: tuple[OidcConfiguration, IdTokenVerifier] | None = None

    @classmethod
    def oauth2(
        cls,
        *,
        id: str,
        issuer: str,
        endpoints: OAuth2Endpoints,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        scopes: Sequence[str] = (),
        subject_field: str = "sub",
        response_issuer: str | None = None,
        claim_mapper: ClaimMapper = default_claim_mapper,
        token_hook: TokenHook | None = None,
        timeout: float = 5.0,
        token_endpoint_auth_method: str = "client_secret_basic",  # noqa: S107  # identifier name, not a secret
    ) -> Self:
        """Build a provider for an OAuth 2.0 server that issues no ID token.

        The flow keeps ``state`` and PKCE and sends no nonce. After the code
        exchange the user endpoint is called with the access token; its JSON
        object is the claim set, with ``iss`` set to *issuer* and ``sub`` set to
        the *subject_field* member as a string (numbers are stringified), then
        passed to *claim_mapper*.

        Args:
            id: The provider ID.
            issuer: The fixed issuer of the identities.
            endpoints: The provider's endpoints.
            client_id: The registered client.
            client_secret: The client's secret; ``None`` for a public client.
            redirect_uri: The registered callback URL.
            scopes: The requested scopes.
            subject_field: The user-endpoint member that is the subject, such
                as ``"id"``.
            response_issuer: The ``iss`` the authorization response must carry;
                ``None`` skips the check, as for a provider that sends none.
            claim_mapper: Replaces :func:`default_claim_mapper`.
            token_hook: Called with the identity and the upstream tokens.
            timeout: Seconds before a back-channel request fails.
            token_endpoint_auth_method: How the client authenticates at the
                token endpoint.
        """
        return cls(
            id=id,
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            claim_mapper=claim_mapper,
            token_hook=token_hook,
            timeout=timeout,
            token_endpoint_auth_method=token_endpoint_auth_method,
            endpoints=endpoints,
            subject_field=subject_field,
            response_issuer=response_issuer,
        )

    def begin(self, request: LoginRequest, *, return_to: str) -> LoginStart:
        """Return the authorization redirect and the transaction to persist.

        Raises:
            TokenVerificationError: Discovery failed or lacks an endpoint.
        """
        if self._endpoints is None:
            endpoint = self._endpoint(
                self._configuration()[0], "authorization_endpoint"
            )
        else:
            endpoint = self._endpoints.authorization
            _require_secure_url(endpoint)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32) if self._endpoints is None else None
        verifier = secrets.token_urlsafe(64)
        params: dict[str, Any] = {}
        if nonce is not None:
            params["nonce"] = nonce
        if self._max_age is not None and self._endpoints is None:
            params["max_age"] = self._max_age
        # Authlib's stubs leave create_authorization_url partly Unknown.
        session = cast(Any, self._session())
        url, _ = session.create_authorization_url(
            endpoint, state=state, code_verifier=verifier, **params
        )
        transaction = LoginTransaction(
            id=secrets.token_urlsafe(32),
            provider=self.id,
            return_to=return_to,
            created_at=datetime.now(UTC),
            state=state,
            nonce=nonce,
            code_verifier=verifier,
        )
        return LoginStart(transaction=transaction, redirect_url=url)

    def complete(
        self, request: LoginRequest, transaction: LoginTransaction
    ) -> ExternalIdentity:
        """Validate the callback in *request* against *transaction*.

        Raises:
            LoginFailed: ``access_denied`` when the provider reported
                ``error=access_denied``; ``login_failed`` for every other
                failure. The reason is for logs.
        """
        try:
            return self._complete(request.query, transaction)
        except (TokenVerificationError, AuthlibBaseError, OSError, ValueError) as exc:
            raise LoginFailed("login_failed", f"{type(exc).__name__}: {exc}") from exc

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        """Return the provider's RP-initiated logout URL, if enabled.

        The URL is the discovered ``end_session_endpoint`` with
        ``id_token_hint`` (the session's ID token), ``post_logout_redirect_uri``
        and ``client_id``.

        Returns:
            The URL, or ``None`` when RP-initiated logout is not enabled, the
            provider is OAuth 2.0, the provider advertises no
            ``end_session_endpoint`` or the session kept no ID token.
        """
        if (
            not self._rp_initiated_logout
            or self._endpoints is not None
            or not session.id_token
        ):
            return None
        endpoint = self._configuration()[0].metadata.get("end_session_endpoint")
        if not isinstance(endpoint, str):
            return None
        _require_secure_url(endpoint)
        query = urlencode(
            {
                "id_token_hint": session.id_token,
                "post_logout_redirect_uri": post_logout_redirect,
                "client_id": self._client_id,
            }
        )
        return f"{endpoint}{'&' if urlsplit(endpoint).query else '?'}{query}"

    def _complete(
        self, query: Mapping[str, str], transaction: LoginTransaction
    ) -> ExternalIdentity:
        configuration = self._configuration()[0] if self._endpoints is None else None
        self._check_callback(query, transaction, configuration)
        code = query.get("code")
        if not code or not transaction.code_verifier:
            raise LoginFailed("login_failed", "callback lacks a code")
        session = self._session()
        token_endpoint = (
            self._endpoints.token
            if self._endpoints is not None
            else self._endpoint(self._configuration()[0], "token_endpoint")
        )
        _require_secure_url(token_endpoint)
        token = cast(
            Mapping[str, Any],
            cast(Any, session).fetch_token(
                token_endpoint,
                grant_type="authorization_code",
                code=code,
                code_verifier=transaction.code_verifier,
            ),
        )
        access_token = token.get("access_token")
        if not isinstance(access_token, str):
            raise LoginFailed("login_failed", "token response lacks an access token")
        raw_id_token: str | None = None
        if self._endpoints is not None:
            claims = self._oauth2_claims(session, self._endpoints)
        else:
            raw_id_token = token.get("id_token")
            if not isinstance(raw_id_token, str) or not transaction.nonce:
                raise LoginFailed("login_failed", "token response lacks an ID token")
            claims = self._oidc_claims(
                session, raw_id_token, access_token, transaction.nonce
            )
        identity = self._claim_mapper(self.id, claims)
        if self._rp_initiated_logout and raw_id_token is not None:
            identity = replace(identity, id_token=raw_id_token)
        self._run_token_hook(identity, token, access_token, raw_id_token)
        return identity

    def _check_callback(
        self,
        query: Mapping[str, str],
        transaction: LoginTransaction,
        configuration: OidcConfiguration | None,
    ) -> None:
        expected_state = transaction.state or ""
        if not expected_state or not secrets.compare_digest(
            query.get("state", "").encode(), expected_state.encode()
        ):
            raise LoginFailed("login_failed", "state does not match the transaction")
        self._check_response_issuer(query, configuration)
        error = query.get("error")
        if error is not None:
            code = "access_denied" if error == "access_denied" else "login_failed"
            raise LoginFailed(code, f"provider returned error {error}")

    def _run_token_hook(
        self,
        identity: ExternalIdentity,
        token: Mapping[str, Any],
        access_token: str,
        raw_id_token: str | None,
    ) -> None:
        if self._token_hook is None:
            return
        refresh = token.get("refresh_token")
        scope = token.get("scope")
        self._token_hook(
            identity,
            UpstreamTokens(
                access_token=access_token,
                id_token=raw_id_token,
                refresh_token=refresh if isinstance(refresh, str) else None,
                scope=scope if isinstance(scope, str) else None,
            ),
        )

    def _oidc_claims(
        self, session: OAuth2Session, id_token: str, access_token: str, nonce: str
    ) -> dict[str, Any]:
        configuration, id_verifier = self._configuration()
        claims = dict(
            id_verifier.verify(id_token, nonce=nonce, access_token=access_token)
        )
        if self._wants_userinfo(claims):
            claims = {**self._fetch_userinfo(session, configuration, claims), **claims}
        return claims

    def _oauth2_claims(
        self, session: OAuth2Session, endpoints: OAuth2Endpoints
    ) -> dict[str, Any]:
        _require_secure_url(endpoints.user)
        response = session.get(endpoints.user, timeout=self._timeout)
        response.raise_for_status()
        user = cast(object, response.json())
        if not isinstance(user, Mapping):
            raise LoginFailed("login_failed", "user endpoint did not return an object")
        claims = dict(cast(Mapping[str, Any], user))
        subject = claims.get(self._subject_field)
        if isinstance(subject, int) and not isinstance(subject, bool):
            subject = str(subject)
        if not isinstance(subject, str) or not subject:
            raise LoginFailed(
                "login_failed", f"user has no usable {self._subject_field}"
            )
        return {**claims, "iss": self._issuer, "sub": subject}

    def _check_response_issuer(
        self, query: Mapping[str, str], configuration: OidcConfiguration | None
    ) -> None:
        if configuration is None:
            expected, required = (
                self._response_issuer,
                self._response_issuer is not None,
            )
        else:
            expected = configuration.issuer
            required = (
                configuration.metadata.get(
                    "authorization_response_iss_parameter_supported"
                )
                is True
            )
        issuer = query.get("iss")
        if issuer is None:
            if required:
                raise LoginFailed("login_failed", "response lacks iss")
        elif expected is not None and issuer != expected:
            raise LoginFailed(
                "login_failed", f"response iss {issuer} is not the issuer"
            )

    def _wants_userinfo(self, claims: Mapping[str, Any]) -> bool:
        if self._userinfo == "auto":
            return "email" not in claims
        return self._userinfo == "always"

    def _fetch_userinfo(
        self,
        session: OAuth2Session,
        configuration: OidcConfiguration,
        claims: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        endpoint = configuration.metadata.get("userinfo_endpoint")
        if not isinstance(endpoint, str):
            if self._userinfo == "always":
                raise LoginFailed("login_failed", "provider has no userinfo_endpoint")
            return {}
        _require_secure_url(endpoint)
        response = session.get(endpoint, timeout=self._timeout)
        response.raise_for_status()
        info = cast(object, response.json())
        if not isinstance(info, Mapping):
            raise LoginFailed("login_failed", "UserInfo is not a JSON object")
        info = cast(Mapping[str, Any], info)
        if info.get("sub") != claims.get("sub"):
            raise LoginFailed("login_failed", "UserInfo sub differs from ID token sub")
        return {name: value for name, value in info.items() if name != "iss"}

    def _session(self) -> OAuth2Session:
        return OAuth2Session(
            self._client_id,
            self._client_secret,
            scope=" ".join(self._scopes) or None,
            redirect_uri=self._redirect_uri,
            token_endpoint_auth_method=self._auth_method,
            code_challenge_method="S256",
            default_timeout=self._timeout,
        )

    def _configuration(self) -> tuple[OidcConfiguration, IdTokenVerifier]:
        if self._discovered is None:
            configuration = discover_oidc(self._issuer, fetch=self._fetch)
            verifier = IdTokenVerifier.from_jwks_url(
                configuration.jwks_uri,
                issuer=configuration.issuer,
                client_id=self._client_id,
                algorithms=self._algorithms,
                leeway=self._leeway,
                max_age=self._max_age,
            )
            self._discovered = (configuration, verifier)
        return self._discovered

    @staticmethod
    def _endpoint(configuration: OidcConfiguration, name: str) -> str:
        endpoint = configuration.metadata.get(name)
        if not isinstance(endpoint, str):
            raise TokenVerificationError("Discovery document has no {}", name)
        _require_secure_url(endpoint)
        return endpoint


@dataclass(frozen=True)
class LogoutRevocation:
    """What a valid back-channel logout token asks to revoke.

    With a ``sid``, revoke that one session: ``ReplayStore.revoke_sid(issuer,
    sid, ...)``. Without one, bump the session version of ``account_id``, or do
    nothing when it is ``None``.

    Attributes:
        issuer: The token's ``iss``.
        sid: The session ID to revoke, if the token names one.
        subject: The token's ``sub``, if present.
        account_id: For a token without ``sid``, the account linked to
            ``(issuer, subject)``; ``None`` when none is linked.
    """

    issuer: str
    sid: str | None = None
    subject: str | None = None
    account_id: str | None = None


class BackchannelLogout:
    """Validates a back-channel logout token and says what it revokes.

    The handler changes no state besides the verifier's ``jti`` record: the
    binding applies the returned :class:`LogoutRevocation`, because the
    revoked-``sid`` lifetime (the sessions' absolute timeout) and the
    session-version store belong to it.

    Args:
        verifier: The logout-token profile for this provider.
        accounts: Finds the account behind ``(issuer, sub)``; never provisions.
    """

    def __init__(
        self, verifier: LogoutTokenVerifier, accounts: AccountResolver
    ) -> None:
        self._verifier = verifier
        self._accounts = accounts

    def handle(self, logout_token: str) -> LogoutRevocation:
        """Verify *logout_token* and return what to revoke.

        A token with a ``sid`` revokes that session only, even if it also has a
        ``sub``.

        Raises:
            TokenVerificationError: The token fails the logout-token profile,
                including a replayed ``jti``. The message is for logs; answer
                ``400``.
        """
        claims = self._verifier.verify(logout_token)
        issuer = cast(str, claims["iss"])
        sid, subject = claims.get("sid"), claims.get("sub")
        if isinstance(sid, str) and sid:
            return LogoutRevocation(
                issuer, sid=sid, subject=subject if isinstance(subject, str) else None
            )
        if not isinstance(subject, str) or not subject:
            raise TokenVerificationError("Logout token has no usable sid or sub")
        return LogoutRevocation(
            issuer,
            subject=subject,
            account_id=self._accounts.lookup(issuer, subject),
        )
