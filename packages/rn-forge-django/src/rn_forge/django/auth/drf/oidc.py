"""JWKS bearer authentication for externally issued tokens in DRF."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, override

from rn_forge.auth import Authenticator, Principal, principal_from_claims
from rn_forge.auth.oidc import OidcAuthenticator
from rn_forge.django.auth.drf.principal import PrincipalBearerAuthentication

__all__ = ["JWKSBearerAuthentication"]


class JWKSBearerAuthentication(PrincipalBearerAuthentication):
    """Authenticate a bearer token against a remote OIDC JWKS endpoint.

    Set ``jwks_url``, ``issuer`` and ``audience`` on a subclass. Authenticators
    and key sets are cached per subclass and process.

    Verification and the claims-to-principal mapping are
    :class:`rn_forge.auth.oidc.OidcAuthenticator`'s, so this stack accepts the
    same tokens as a FastAPI service wired to the same IdP. Accounts are linked
    as in :class:`PrincipalBearerAuthentication`, so set ``accounts`` and
    ``contexts`` too.
    """

    jwks_url: ClassVar[str]
    issuer: ClassVar[str]
    audience: ClassVar[str | Sequence[str]]
    algorithms: ClassVar[Sequence[str]] = ("RS256",)
    cache_timeout: ClassVar[float] = 300.0
    """Seconds a fetched key set stays cached."""
    cooldown_duration: ClassVar[float] = 30.0
    """The fewest seconds between two key set fetches."""
    leeway: ClassVar[float] = 0.0

    _authenticators: ClassVar[dict[type, Authenticator]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def claims_to_principal(self, claims: Mapping[str, Any]) -> Principal:
        """Map verified claims to the principal on ``request.user``."""
        return principal_from_claims(claims)

    @override
    def get_authenticator(self) -> Authenticator:
        cls = type(self)
        with cls._lock:
            authenticator = cls._authenticators.get(cls)
            if authenticator is None:
                authenticator = OidcAuthenticator.from_jwks_url(
                    cls.jwks_url,
                    issuer=cls.issuer,
                    audience=cls.audience,
                    claims_to_principal=self.claims_to_principal,
                    algorithms=cls.algorithms,
                    leeway=cls.leeway,
                    lifespan=cls.cache_timeout,
                    cooldown_duration=cls.cooldown_duration,
                )
                cls._authenticators[cls] = authenticator
        return authenticator
