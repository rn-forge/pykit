"""The OIDC bearer authenticator both framework bindings share.

Joins the two halves of the auth story: ``rn-forge-commons`` verifies a token
and returns claims, :mod:`rn_forge.web.auth` says what a caller is and what a
refusal looks like. This module is the one implementation that connects them,
so a Django service and a FastAPI service accept the same tokens and produce
the same :class:`~rn_forge.web.auth.Principal`.

Requires the ``auth`` extra (``rn-forge-commons[auth]``, which brings PyJWT).
Not imported by ``rn_forge.web``'s curated ``__init__.py``; import this module
directly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Self

from rn_forge.commons.integration.auth import (
    FetchJson,
    JwksCache,
    JwtVerifier,
    TokenVerificationError,
    fetch_json,
)

from rn_forge.web.auth import (
    Credentials,
    Principal,
    principal_from_claims,
)
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = ["OidcAuthenticator"]

type ClaimsToPrincipal = Callable[[Mapping[str, Any]], Principal]


class OidcAuthenticator:
    """An :class:`~rn_forge.web.auth.Authenticator` backed by a :class:`JwtVerifier`.

    Build one at startup and reuse it: the verifier holds the JWKS cache, so a
    per-request instance refetches the key set on every call.

    The reason a token was rejected is carried on the raised
    :class:`~rn_forge.web.exceptions.AuthenticationFailed` for the binding to
    log. It never reaches the response body — both framework packages render a
    401 with :data:`~rn_forge.web.auth.AUTH_FAILED_DETAIL`.

    Args:
        verifier: Verifies the bearer token and returns its claims.
        claims_to_principal: Verified claims → principal. Defaults to
            :func:`~rn_forge.web.auth.principal_from_claims`; override it for
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
        max_age: float = 86_400.0,
    ) -> Self:
        """Build an authenticator by OIDC discovery on *issuer*.

        Discovery runs once, here — so call this at startup, not per request.

        Args:
            issuer: The IdP's issuer URL. Its
                ``/.well-known/openid-configuration`` supplies the ``jwks_uri``.
            audience: The ``aud`` accepted — one value, or any of several.
            claims_to_principal: See the class docstring.
            fetch: The JSON transport, for a proxy or a test double.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age: Seconds a fetched key set stays cached.

        Raises:
            TokenVerificationError: Discovery failed or returned no ``jwks_uri``.
        """
        return cls(
            JwtVerifier.from_issuer(
                issuer,
                audience=audience,
                fetch=fetch,
                algorithms=algorithms,
                leeway=leeway,
                max_age=max_age,
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
        fetch: FetchJson = fetch_json,
        algorithms: Sequence[str] = ("RS256",),
        leeway: float = 0.0,
        max_age: float = 86_400.0,
    ) -> Self:
        """Build an authenticator from a known JWKS URL, skipping discovery.

        For an IdP that publishes no discovery document, or a deployment that
        pins the key-set URL.

        Args:
            jwks_url: Where the key set is served.
            issuer: The exact ``iss`` accepted.
            audience: The ``aud`` accepted — one value, or any of several.
            claims_to_principal: See the class docstring.
            fetch: The JSON transport, for a proxy or a test double.
            algorithms: The signature algorithms accepted.
            leeway: Seconds of clock skew tolerated.
            max_age: Seconds a fetched key set stays cached.
        """
        return cls(
            JwtVerifier(
                jwks=JwksCache(jwks_url, fetch=fetch, max_age=max_age),
                issuer=issuer,
                audience=audience,
                algorithms=algorithms,
                leeway=leeway,
            ),
            claims_to_principal=claims_to_principal,
        )

    def authenticate(self, *, credentials: Credentials) -> Principal:
        """See :meth:`rn_forge.web.auth.Authenticator.authenticate`.

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
