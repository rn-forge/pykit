"""FastAPI security dependencies for the authentication contracts.

Framework credential parsers run with ``auto_error=False`` so failures use the
shared problem response and challenge behavior.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import cast

from fastapi import Depends, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)
from rn_forge.auth import (
    AccountResolver,
    AsyncAuthenticator,
    Authenticator,
    AuthorizationContext,
    AuthorizationContextProvider,
    Authorizer,
    Principal,
    Requirement,
    ScopeAuthorizer,
    audit,
    effective_permissions,
    requirement_for,
)
from rn_forge.fastapi.auth.sessions import ActiveSession, active_session
from rn_forge.fastapi.problem import Log
from rn_forge.web import (
    AuthenticationFailed,
    Credentials,
    PermissionDenied,
    SessionRequired,
    parse_authorization,
)

__all__ = [
    "BearerAuth",
    "basic_auth",
    "bearer_auth",
    "current_principal",
    "requires",
    "requires_permission",
]

_BEARER = HTTPBearer(auto_error=False)

type PrincipalDependency = Callable[..., Awaitable[Principal]]


class BearerAuth:
    """A dependency yielding the :class:`rn_forge.auth.Principal` for a Bearer token.

    Build it with :func:`bearer_auth`; use the instance as a dependency, or pass
    it to :func:`current_principal`.
    """

    def __init__(
        self,
        *,
        authenticator: Authenticator | AsyncAuthenticator,
        accounts: AccountResolver,
        contexts: AuthorizationContextProvider,
        scope_map: Mapping[str, frozenset[str]],
        log: Log | None,
    ) -> None:
        self._authenticator = authenticator
        self._accounts = accounts
        self._contexts = contexts
        self._scope_map = scope_map
        self._log = log

    async def authenticate(self, request: Request) -> Principal:
        """Return the principal for the request's Bearer token.

        Raises:
            AuthenticationFailed: The token is absent, invalid or has no linked
                active account.
        """
        credentials = parse_authorization(
            request.headers.get("Authorization"), "Bearer"
        )
        if credentials is None or not credentials.token:
            raise AuthenticationFailed("No credentials were supplied", error_code=401)
        verified = await _authenticate(self._authenticator, credentials, self._log)
        try:
            return await run_in_threadpool(self._link, verified)
        except AuthenticationFailed as exc:
            if self._log is not None:
                self._log(
                    "authentication.failed",
                    {"scheme": "Bearer", "reason": exc.message},
                )
            raise

    def _link(self, principal: Principal) -> Principal:
        account_id = (
            self._accounts.lookup(principal.issuer, principal.subject)
            if principal.issuer
            else None
        )
        if account_id is None:
            raise AuthenticationFailed("No account is linked to the token subject")
        context = self._contexts.resolve(account_id)
        if not context.active:
            raise AuthenticationFailed("The account is not active")
        return replace(
            principal,
            subject=account_id,
            external_subject=principal.subject,
            permissions=effective_permissions(
                context.permissions,
                mechanism="bearer",
                scopes=principal.scopes,
                scope_map=self._scope_map,
            ),
            roles=context.roles,
            tenant=_tenant(context),
            attributes=context.attributes,
        )

    async def __call__(
        self,
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Security(_BEARER),
    ) -> Principal:
        return await self.authenticate(request)


def bearer_auth(
    *,
    authenticator: Authenticator | AsyncAuthenticator,
    accounts: AccountResolver,
    contexts: AuthorizationContextProvider,
    scope_map: Mapping[str, frozenset[str]] | None = None,
    log: Log | None = None,
) -> BearerAuth:
    """Return a dependency yielding the :class:`rn_forge.auth.Principal` for a Bearer token.

    The verified token's ``(issuer, subject)`` is looked up with
    ``accounts.lookup``, which never provisions. A token with no linked
    account, or whose account is inactive, is a 401. The principal's
    ``subject`` is then the account ID (``external_subject`` keeps the token's);
    its roles, tenant and attributes come from the account's authorization
    context, and its permissions are the context's limited by the token's
    scopes through *scope_map*.

    Args:
        authenticator: Verifies ``Credentials(scheme="Bearer", token=...)``.
        accounts: Links the token's identity to an account.
        contexts: Supplies the account's authorization context.
        scope_map: The permissions each accepted scope allows; a scope it does
            not name allows nothing.
        log: Receives ``authentication.failed`` with the failure's reason.
            The 401 body never carries it.
    """
    return BearerAuth(
        authenticator=authenticator,
        accounts=accounts,
        contexts=contexts,
        scope_map=scope_map if scope_map is not None else {},
        log=log,
    )


def current_principal(*, bearer: BearerAuth | None = None) -> PrincipalDependency:
    """Return a dependency yielding the session or bearer principal.

    A request with an ``Authorization`` header is authenticated by *bearer*
    alone: an invalid token is a 401 even with a valid session cookie, and
    without *bearer* the header makes the request unauthenticated. Any other
    request is authenticated by the login session that
    :class:`~rn_forge.fastapi.SessionMiddleware` resolved, whose principal has
    ``mechanism="session"``, the context's roles and permissions, and the
    session's ``auth_time`` and ``amr``. CSRF checks for session requests are
    the middleware's.

    An unauthenticated request is a 401 with the ``Bearer`` challenge when
    *bearer* is given, and without a challenge otherwise.

    Args:
        bearer: From :func:`bearer_auth`.

    Raises:
        RuntimeError: At request time, :class:`~rn_forge.fastapi.SessionMiddleware`
            is not installed and the request carries no ``Authorization`` header.
    """

    async def resolve(request: Request) -> Principal:
        if "Authorization" in request.headers:
            if bearer is None:
                raise SessionRequired("Authorization header without bearer auth")
            return await bearer.authenticate(request)
        active = active_session(request)
        if active is None:
            if bearer is None:
                raise SessionRequired("No session")
            raise AuthenticationFailed("No credentials were supplied", error_code=401)
        return _session_principal(active)

    if bearer is None:

        async def session_dependency(request: Request) -> Principal:
            return await resolve(request)

        return session_dependency

    async def dependency(
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Security(_BEARER),
    ) -> Principal:
        return await resolve(request)

    return dependency


def _tenant(context: AuthorizationContext) -> str | None:
    tenant = context.attributes.get("tenant")
    return tenant if isinstance(tenant, str) else None


def _session_principal(active: ActiveSession) -> Principal:
    info, context = active.info, active.context
    return Principal(
        subject=info.account_id,
        issuer=info.issuer,
        external_subject=info.external_subject,
        permissions=context.permissions,
        roles=context.roles,
        tenant=_tenant(context),
        attributes=context.attributes,
        mechanism="session",
        auth_time=info.auth_time,
        amr=info.amr,
    )


def basic_auth(
    *, authenticator: Authenticator | AsyncAuthenticator, log: Log | None = None
) -> PrincipalDependency:
    """Return a dependency yielding a principal for HTTP Basic credentials.

    Args:
        authenticator: Verifies ``Credentials(scheme="Basic", token=...)``, where
            the token is the base64 parameter exactly as sent (RFC 7617).
        log: Receives ``authentication.failed`` with the authenticator's reason.
    """
    scheme = HTTPBasic(auto_error=False)

    async def dependency(
        request: Request,
        basic: HTTPBasicCredentials | None = Security(scheme),
    ) -> Principal:
        credentials = parse_authorization(request.headers.get("Authorization"), "Basic")
        if basic is None or credentials is None:
            raise AuthenticationFailed("No credentials were supplied", error_code=401)
        return await _authenticate(authenticator, credentials, log)

    return dependency


def requires(
    authenticate: PrincipalDependency,
    requirement: Requirement,
    *,
    authorizer: Authorizer | None = None,
) -> PrincipalDependency:
    """Return a dependency that authenticates, then enforces *requirement*.

    Insufficient access produces 403 without an authentication challenge.

    Args:
        authenticate: A dependency from :func:`bearer_auth`, :func:`basic_auth`
            or :func:`current_principal`.
        requirement: Evaluated by :class:`rn_forge.auth.Requirement`'s own rule.
        authorizer: Defaults to :class:`rn_forge.auth.ScopeAuthorizer`.
    """
    resolved = authorizer if authorizer is not None else ScopeAuthorizer()

    async def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        try:
            resolved.authorize(principal, requires=requirement)
        except PermissionDenied:
            audit("authorization.denied", account_id=principal.subject)
            raise
        return principal

    return dependency


def requires_permission(
    authenticate: PrincipalDependency,
    permission_key: str,
    action: str,
    *,
    action_map: Mapping[str, str] | None = None,
    authorizer: Authorizer | None = None,
) -> PrincipalDependency:
    """Return a dependency that authenticates, then enforces a permission key.

    The requirement is :func:`rn_forge.auth.requirement_for` of *permission_key*
    and the action. Insufficient access produces 403 without a challenge.

    Args:
        authenticate: A dependency such as :func:`current_principal`'s.
        permission_key: The resource's base permission key, such as ``orders``.
        action: The action to check, such as ``list``, ``retrieve`` or
            ``partial_update``.
        action_map: Overrides of ``DEFAULT_PERMISSION_ACTION_MAP``.
        authorizer: Defaults to :class:`rn_forge.auth.ScopeAuthorizer`.
    """
    resolved = authorizer if authorizer is not None else ScopeAuthorizer()

    requirement = requirement_for(permission_key, action, action_map=action_map)

    async def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        try:
            resolved.authorize(principal, requires=requirement)
        except PermissionDenied:
            audit(
                "authorization.denied",
                account_id=principal.subject,
                permission_key=permission_key,
                action=action,
            )
            raise
        return principal

    return dependency


async def _authenticate(
    authenticator: Authenticator | AsyncAuthenticator,
    credentials: Credentials,
    log: Log | None,
) -> Principal:
    """Run a sync or async authenticator, logging the reason for a refusal.

    A synchronous authenticator runs in the threadpool, as FastAPI runs a sync
    dependency, so its network I/O (a JWKS fetch, say) does not block the loop.
    """
    try:
        if inspect.iscoroutinefunction(authenticator.authenticate):
            outcome = authenticator.authenticate(credentials=credentials)
        else:
            authenticate = cast(
                Callable[..., Principal | Awaitable[Principal]],
                authenticator.authenticate,
            )
            outcome = await run_in_threadpool(authenticate, credentials=credentials)
        return outcome if isinstance(outcome, Principal) else await outcome
    except AuthenticationFailed as exc:
        if log is not None:
            log(
                "authentication.failed",
                {"scheme": credentials.scheme, "reason": exc.message},
            )
        raise
