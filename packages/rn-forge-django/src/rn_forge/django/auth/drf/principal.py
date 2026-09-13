"""The DRF binding of the :mod:`rn_forge.web.auth` contract.

The contract — :class:`rn_forge.web.Principal`, the authenticator and authorizer
protocols, the 401/403 boundary and the RFC 6750 challenge — is
``rn-forge-web``'s. This module only lifts credentials off a DRF request, hands
them to an authenticator and puts the principal on ``request.user``; it verifies
nothing itself. ``rn-forge-fastapi``'s ``bearer_auth``/``basic_auth`` are its
twins and produce the same principal and the same wire failures.

**Bound to** :class:`rn_forge.web.Authenticator`, **not to a token verifier.**
Verifying a JWT against an OIDC JWKS endpoint is the authenticator's job, over
whatever verifier the application uses; commons has no such module yet, and when
it lands it sits behind the same protocol, so nothing here changes.

This is a different mechanism from ``rn_forge.django.auth.jwt``, which issues
and verifies simplejwt tokens against a local ``User``. Here there is no local
user: ``request.user`` *is* the principal.

The failure wire shape
----------------------

Both classes raise DRF's ``AuthenticationFailed`` carrying only
:data:`rn_forge.web.AUTH_FAILED_DETAIL`, and build their challenge with
:func:`rn_forge.web.challenge_header`, so with
:func:`rn_forge.django.drf.exceptions.problem_details_exception_handler`
installed a 401 is ``application/problem+json`` with an RFC 6750
``WWW-Authenticate`` header, and a 403 from :func:`requires` carries none. The
reason verification failed is logged at debug and never sent.

Configuration is by subclass, because ``authentication_classes`` names classes::

    class ApiBearer(PrincipalBearerAuthentication):
        authenticator = MyJwksAuthenticator(...)
        realm = "orders"

    class OrderView(APIView):
        authentication_classes = [ApiBearer]
        permission_classes = [requires(Requirement(all_scopes=frozenset({"orders:read"})))]
"""

from __future__ import annotations

from typing import Any, ClassVar, override

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed as DRFAuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rn_forge.commons.logging import AppLogger
from rn_forge.django.drf import RequestUtils
from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    AuthenticationFailed,
    Authenticator,
    Authorizer,
    Credentials,
    Principal,
    Requirement,
    ScopeAuthorizer,
    challenge_header,
)

__all__ = [
    "PrincipalBasicAuthentication",
    "PrincipalBearerAuthentication",
    "requires",
]

_LOGGER = AppLogger.get_logger(__name__)


class _PrincipalAuthentication(BaseAuthentication):
    """Shared plumbing: one ``Authorization`` scheme, one authenticator."""

    scheme: ClassVar[str]
    authenticator: ClassVar[Authenticator]
    realm: ClassVar[str | None] = None

    @override
    def authenticate(self, request: Request) -> tuple[Principal, Credentials] | None:
        header = RequestUtils.get_django_request(request).headers.get("Authorization")
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != self.scheme.lower():
            return None
        credentials = Credentials(self.scheme, token.strip())
        try:
            if not credentials.token:
                raise AuthenticationFailed("Empty {} credentials", self.scheme)
            principal = self.get_authenticator().authenticate(credentials=credentials)
        except AuthenticationFailed as exc:
            _LOGGER.debug(
                "Authentication failed: scheme={} reason={}", self.scheme, exc.message
            )
            raise DRFAuthenticationFailed(AUTH_FAILED_DETAIL) from exc
        return principal, credentials

    def get_authenticator(self) -> Authenticator:
        """Return the authenticator to verify with: the ``authenticator`` attribute.

        Override to build one lazily, as ``JWKSBearerAuthentication`` does.
        """
        return self.authenticator

    @override
    def authenticate_header(self, request: Request) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]  # DRF stubs type the base as returning None; DRF reads a str
        return challenge_header(scheme=self.scheme, realm=self.realm)


class PrincipalBearerAuthentication(_PrincipalAuthentication):
    """Authenticate ``Authorization: Bearer <token>`` into a :class:`rn_forge.web.Principal`.

    Subclass and set ``authenticator`` (and ``realm``). A request with no
    ``Authorization`` header, or another scheme, is left to the next
    authentication class; an empty or rejected bearer token is a 401.
    """

    scheme: ClassVar[str] = "Bearer"


class PrincipalBasicAuthentication(_PrincipalAuthentication):
    """Authenticate HTTP Basic (RFC 7617) into a :class:`rn_forge.web.Principal`.

    **For local development and simple internal deployments only.** A password
    on every request is not a production mechanism, and producing the same
    ``Principal`` and the same 401 as the bearer class does not make it one.

    The authenticator receives the base64 credential exactly as sent.
    """

    scheme: ClassVar[str] = "Basic"


def requires(
    requirement: Requirement, *, authorizer: Authorizer | None = None
) -> type[BasePermission]:
    """Return a DRF permission class enforcing *requirement* on the principal.

    No principal on the request — no credentials were sent — makes DRF answer
    401 with the first authentication class's challenge. A principal lacking the
    access raises :class:`rn_forge.web.PermissionDenied`: 403, no challenge. The
    requirement is evaluated by :class:`rn_forge.web.Requirement`'s own rule,
    identically to FastAPI.

    Args:
        requirement: The scopes and roles demanded.
        authorizer: Defaults to :class:`rn_forge.web.ScopeAuthorizer`.
    """
    resolved = authorizer if authorizer is not None else ScopeAuthorizer()

    class RequirementPermission(BasePermission):
        @override
        def has_permission(self, request: Request, view: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
            principal = RequestUtils.get_request_user(request)
            if not isinstance(principal, Principal):
                return False
            resolved.authorize(principal, requires=requirement)
            return True

    return RequirementPermission
