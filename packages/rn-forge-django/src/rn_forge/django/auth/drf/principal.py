"""Bind ``rn_forge.auth`` principal authentication to DRF requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, ClassVar, override

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed as DRFAuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rn_forge.auth import (
    AccountResolver,
    Authenticator,
    AuthorizationContextProvider,
    Authorizer,
    Principal,
    Requirement,
    ScopeAuthorizer,
    effective_permissions,
)
from rn_forge.commons.logging import AppLogger
from rn_forge.django.drf import RequestUtils
from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    AuthenticationFailed,
    Credentials,
    challenge_header,
    parse_authorization,
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
        credentials = parse_authorization(
            RequestUtils.get_django_request(request).headers.get("Authorization"),
            self.scheme,
        )
        if credentials is None:
            return None
        try:
            if not credentials.token:
                raise AuthenticationFailed("Empty {} credentials", self.scheme)
            principal = self.get_authenticator().authenticate(credentials=credentials)
            principal = self.link_principal(principal)
        except AuthenticationFailed as exc:
            _LOGGER.debug(  # noqa: PLE1205  # brace-style log format
                "Authentication failed: scheme={} reason={}", self.scheme, exc.message
            )
            raise DRFAuthenticationFailed(AUTH_FAILED_DETAIL) from exc
        return principal, credentials

    def link_principal(self, principal: Principal) -> Principal:
        """Return *principal* as the caller to act as."""
        return principal

    def get_authenticator(self) -> Authenticator:
        """Return the authenticator to verify with: the ``authenticator`` attribute.

        Override to build one lazily, as ``JWKSBearerAuthentication`` does.
        """
        return self.authenticator

    @override
    def authenticate_header(self, request: Request) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]  # DRF stubs type the base as returning None; DRF reads a str
        return challenge_header(scheme=self.scheme, realm=self.realm)


class PrincipalBearerAuthentication(_PrincipalAuthentication):
    """Authenticate ``Authorization: Bearer <token>`` into a :class:`rn_forge.auth.Principal`.

    Subclass and set ``authenticator``, ``accounts``, ``contexts`` and,
    optionally, ``realm`` and ``scope_map``.

    The verified token's ``(issuer, subject)`` is looked up with
    ``accounts.lookup``, which never provisions. A token with no linked
    account, or whose account is inactive, is a ``401``. The principal's
    ``subject`` is then the account ID (``external_subject`` keeps the token's),
    its roles, tenant and attributes come from the account's authorization
    context, and its permissions are the context's limited by the token's
    scopes through ``scope_map`` (a scope the map does not name allows nothing).
    """

    scheme: ClassVar[str] = "Bearer"
    accounts: ClassVar[AccountResolver]
    contexts: ClassVar[AuthorizationContextProvider]
    scope_map: ClassVar[Mapping[str, frozenset[str]]] = {}

    @override
    def link_principal(self, principal: Principal) -> Principal:
        account_id = (
            self.accounts.lookup(principal.issuer, principal.subject)
            if principal.issuer
            else None
        )
        if account_id is None:
            raise AuthenticationFailed("No account is linked to the token subject")
        context = self.contexts.resolve(account_id)
        if not context.active:
            raise AuthenticationFailed("The account is not active")
        tenant = context.attributes.get("tenant")
        return replace(
            principal,
            subject=account_id,
            external_subject=principal.subject,
            permissions=effective_permissions(
                context.permissions,
                mechanism="bearer",
                scopes=principal.scopes,
                scope_map=self.scope_map,
            ),
            roles=context.roles,
            tenant=tenant if isinstance(tenant, str) else None,
            attributes=context.attributes,
        )


class PrincipalBasicAuthentication(_PrincipalAuthentication):
    """Authenticate HTTP Basic (RFC 7617) into a :class:`rn_forge.auth.Principal`.

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
        authorizer: Defaults to :class:`rn_forge.auth.ScopeAuthorizer`.
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
