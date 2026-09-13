"""JWKS bearer authentication for DRF: externally issued tokens, no local user.

Requires the ``oidc`` extra. Not re-exported from ``rn_forge.django.auth.drf``;
import it from here.

The layers, each in its own package:

- **Verification** — :class:`rn_forge.commons.integration.auth.JwtVerifier`:
  JWKS fetch and rotation, signature, ``exp``/``aud``/``iss``.
- **Claims → principal** — :func:`rn_forge.web.principal_from_claims`, the same
  default an ``rn-forge-fastapi`` service uses.
- **The DRF binding and the 401/403 wire shape** —
  :class:`~rn_forge.django.auth.drf.principal.PrincipalBearerAuthentication`,
  which this subclasses.

Configure by subclass, one per IdP, since ``authentication_classes`` names a
class. The IdP is configuration, never a constant here::

    class EntraBearer(JWKSBearerAuthentication):
        jwks_url = f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys"
        issuer = f"https://login.microsoftonline.com/{TENANT}/v2.0"
        audience = "api://orders"
        realm = "orders"

        def claims_to_principal(self, claims):
            principal = super().claims_to_principal(claims)
            return replace(principal, roles=principal.roles | {"reader"})

The key set is cached per subclass, per process, for ``cache_timeout`` seconds,
and refetched once on an unknown ``kid`` (bounded) so a key rotation is picked
up. It is not stored in Django's cache: a key set is small, per-process state is
enough, and a shared cache would need its own invalidation for no gain.

The drf-spectacular security scheme for this class is registered by
:mod:`rn_forge.django.drf.openapi` (it matches subclasses of the bearer class).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, override

from rn_forge.commons.integration.auth import (
    FetchJson,
    JwksCache,
    JwtVerifier,
    TokenVerificationError,
    fetch_json,
)
from rn_forge.web import (
    AuthenticationFailed,
    Authenticator,
    Credentials,
    Principal,
    principal_from_claims,
)

from rn_forge.django.auth.drf.principal import PrincipalBearerAuthentication

__all__ = ["JWKSAuthenticator", "JWKSBearerAuthentication"]


class JWKSAuthenticator:
    """An :class:`rn_forge.web.Authenticator` over a commons :class:`JwtVerifier`.

    Framework-free; :class:`JWKSBearerAuthentication` builds one per subclass.

    Args:
        verifier: Verifies the bearer token.
        claims_to_principal: Verified claims → principal. Defaults to
            :func:`rn_forge.web.principal_from_claims`.
    """

    def __init__(
        self,
        verifier: JwtVerifier,
        *,
        claims_to_principal: Callable[
            [Mapping[str, Any]], Principal
        ] = principal_from_claims,
    ) -> None:
        self._verifier = verifier
        self._claims_to_principal = claims_to_principal

    def authenticate(self, *, credentials: Credentials) -> Principal:
        """See :meth:`rn_forge.web.Authenticator.authenticate`."""
        try:
            claims = self._verifier.verify(credentials.token)
        except TokenVerificationError as exc:
            raise AuthenticationFailed(exc.message, error_code=401) from exc
        return self._claims_to_principal(claims)


class JWKSBearerAuthentication(PrincipalBearerAuthentication):
    """Authenticate a bearer token against a remote OIDC JWKS endpoint.

    Set ``jwks_url``, ``issuer`` and ``audience`` on a subclass; override
    :meth:`claims_to_principal` to read a deployment's own claim shape.
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
                jwks = JwksCache(
                    cls.jwks_url, fetch=cls.fetch, max_age=cls.cache_timeout
                )
                verifier = JwtVerifier(
                    jwks=jwks,
                    issuer=cls.issuer,
                    audience=cls.audience,
                    algorithms=cls.algorithms,
                    leeway=cls.leeway,
                )
                authenticator = JWKSAuthenticator(
                    verifier, claims_to_principal=self.claims_to_principal
                )
                cls._authenticators[cls] = authenticator
        return authenticator
