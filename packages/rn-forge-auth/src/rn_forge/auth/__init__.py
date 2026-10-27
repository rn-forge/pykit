"""Authentication primitives.

The OIDC adapter, :mod:`rn_forge.auth.oidc`, needs the ``oidc`` extra and is
imported directly.
"""

from rn_forge.auth.accounts import AccountRejected, AccountResolver
from rn_forge.auth.authorization import (
    AsyncAuthenticator,
    Authenticator,
    Authorizer,
    ScopeAuthorizer,
)
from rn_forge.auth.context import AuthorizationContext, AuthorizationContextProvider
from rn_forge.auth.identity import (
    ExternalIdentity,
    IdentityProvider,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)
from rn_forge.auth.policy import ResourcePolicy
from rn_forge.auth.principal import Principal, Requirement, principal_from_claims

__all__ = [
    "AccountRejected",
    "AccountResolver",
    "AsyncAuthenticator",
    "Authenticator",
    "AuthorizationContext",
    "AuthorizationContextProvider",
    "Authorizer",
    "ExternalIdentity",
    "IdentityProvider",
    "LoginStart",
    "LoginTransaction",
    "Principal",
    "ProviderKind",
    "Requirement",
    "ResourcePolicy",
    "ScopeAuthorizer",
    "SessionInfo",
    "principal_from_claims",
]
