"""FastAPI security dependencies for the web authentication contracts.

Framework credential parsers run with ``auto_error=False`` so failures use the
shared problem response and challenge behavior.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Depends, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from rn_forge.fastapi.problem import Log
from rn_forge.web import (
    AsyncAuthenticator,
    AuthenticationFailed,
    Authenticator,
    Authorizer,
    Credentials,
    Principal,
    Requirement,
    ScopeAuthorizer,
)

__all__ = ["basic_auth", "bearer_auth", "requires"]

type PrincipalDependency = Callable[..., Awaitable[Principal]]


def bearer_auth(
    *, authenticator: Authenticator | AsyncAuthenticator, log: Log | None = None
) -> PrincipalDependency:
    """Return a dependency yielding the :class:`rn_forge.web.Principal` for a Bearer token.

    Args:
        authenticator: Verifies ``Credentials(scheme="Bearer", token=...)``.
        log: Receives ``authentication.failed`` with the authenticator's reason.
            The 401 body never carries it.
    """
    scheme = HTTPBearer(auto_error=False)

    async def dependency(
        credentials: HTTPAuthorizationCredentials | None = Security(scheme),
    ) -> Principal:
        if credentials is None:
            raise AuthenticationFailed("No credentials were supplied", error_code=401)
        return await _authenticate(
            authenticator, Credentials("Bearer", credentials.credentials), log
        )

    return dependency


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
        if basic is None:
            raise AuthenticationFailed("No credentials were supplied", error_code=401)
        token = request.headers["Authorization"].partition(" ")[2].strip()
        return await _authenticate(authenticator, Credentials("Basic", token), log)

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
        authenticate: A dependency from :func:`bearer_auth` or :func:`basic_auth`.
        requirement: Evaluated by :class:`rn_forge.web.Requirement`'s own rule,
            identically to Django.
        authorizer: Defaults to :class:`rn_forge.web.ScopeAuthorizer`.
    """
    resolved = authorizer if authorizer is not None else ScopeAuthorizer()

    async def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        resolved.authorize(principal, requires=requirement)
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
