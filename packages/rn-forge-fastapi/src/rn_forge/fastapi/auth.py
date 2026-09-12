"""The authentication binding: ``Security`` dependencies over the web auth contract.

The contract — :class:`rn_forge.web.Principal`, the authenticator and
authorizer protocols, the 401/403 boundary — is :mod:`rn_forge.web.auth`'s. The
failure wire shape is :func:`rn_forge.fastapi.register_problem_handlers`'. This
module only lifts credentials off the request, hands them to an authenticator
and returns the principal.

**Bound to :class:`rn_forge.web.Authenticator`, not to a token verifier.**
Verifying a JWT against a JWKS is an application's authenticator's job, over
whatever verifier it uses; this binding accepts any object satisfying the web
protocol, sync or async.

FastAPI's ``HTTPBearer``/``HTTPBasic`` are used with ``auto_error=False``,
which keeps what they are good for — the ``securitySchemes`` entry in the
OpenAPI document — and discards what they get wrong: their own 401 body and a
challenge that is not RFC 6750's. Every refusal raises a :mod:`rn_forge.web`
exception, so a UI sees ``problem+json`` for an auth failure like any other.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request, Security
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
    """Return a dependency yielding the :class:`rn_forge.web.Principal` for HTTP Basic.

    **For local development and simple internal deployments only.** A password
    on every request is not a production mechanism, and this does not become
    one by producing the same ``Principal`` and the same 401 as
    :func:`bearer_auth`.

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

    A principal lacking the access is a 403 with no challenge — the caller is
    authenticated; that is the 401/403 boundary.

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
    """Run a sync or async authenticator, logging the reason for a refusal."""
    try:
        outcome = authenticator.authenticate(credentials=credentials)
        return outcome if isinstance(outcome, Principal) else await outcome
    except AuthenticationFailed as exc:
        if log is not None:
            log(
                "authentication.failed",
                {"scheme": credentials.scheme, "reason": exc.message},
            )
        raise
