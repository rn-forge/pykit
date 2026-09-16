"""JWKS bearer authentication for externally issued tokens in DRF."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, override

from rn_forge.commons.integration.auth import FetchJson, fetch_json
from rn_forge.web import Authenticator, Principal, principal_from_claims
from rn_forge.web.oidc import OidcAuthenticator

from rn_forge.django.auth.drf.principal import PrincipalBearerAuthentication

__all__ = ["JWKSBearerAuthentication"]


class JWKSBearerAuthentication(PrincipalBearerAuthentication):
    """Authenticate a bearer token against a remote OIDC JWKS endpoint.

    Set ``jwks_url``, ``issuer`` and ``audience`` on a subclass. Authenticators
    and key sets are cached per subclass and process.

    Verification and the claims-to-principal mapping are
    :class:`rn_forge.web.oidc.OidcAuthenticator`'s, so this stack accepts the
    same tokens as a FastAPI service wired to the same IdP.
    """

    jwks_url: ClassVar[str]
    issuer: ClassVar[str]
    audience: ClassVar[str | Sequence[str]]
    algorithms: ClassVar[Sequence[str]] = ("RS256",)
    cache_timeout: ClassVar[int] = 86_400
    leeway: ClassVar[float] = 0.0
    fetch: ClassVar[FetchJson] = staticmethod(fetch_json)
    """The key-set transport. Replace it for a proxy, or in tests."""

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
                    fetch=cls.fetch,
                    algorithms=cls.algorithms,
                    leeway=cls.leeway,
                    max_age=cls.cache_timeout,
                )
                cls._authenticators[cls] = authenticator
        return authenticator
