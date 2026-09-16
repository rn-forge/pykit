"""Bind ``rn_forge.web`` principal authentication to DRF requests."""

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

    Subclass and set ``authenticator`` and, optionally, ``realm``.
    """

    scheme: ClassVar[str] = "Bearer"


class PrincipalBasicAuthentication(_PrincipalAuthentication):
    """Authenticate HTTP Basic (RFC 7617) into a :class:`rn_forge.web.Principal`.

    Intended for local development and simple internal deployments. The
    authenticator receives the base64 credential exactly as sent.
    """

    scheme: ClassVar[str] = "Basic"


def requires(
    requirement: Requirement, *, authorizer: Authorizer | None = None
) -> type[BasePermission]:
    """Return a DRF permission class enforcing *requirement* on the principal.

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
