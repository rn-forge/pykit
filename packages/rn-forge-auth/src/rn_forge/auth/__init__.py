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
from rn_forge.auth.context_cache import (
    AccountStateWriter,
    AuthorizationContextCache,
    AuthorizationVersions,
    InMemoryAuthorizationVersions,
)
from rn_forge.auth.identity import (
    ExternalIdentity,
    IdentityProvider,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)
from rn_forge.auth.permissions import (
    DEFAULT_PERMISSION_ACTION_MAP,
    effective_permissions,
    requirement_for,
)
from rn_forge.auth.policy import ResourcePolicy
from rn_forge.auth.principal import (
    Mechanism,
    Principal,
    Requirement,
    principal_from_claims,
)
from rn_forge.auth.stores import InMemoryReplayStore, ReplayStore

__all__ = [
    "DEFAULT_PERMISSION_ACTION_MAP",
    "AccountRejected",
    "AccountResolver",
    "AccountStateWriter",
    "AsyncAuthenticator",
    "Authenticator",
    "AuthorizationContext",
    "AuthorizationContextCache",
    "AuthorizationContextProvider",
    "AuthorizationVersions",
    "Authorizer",
    "ExternalIdentity",
    "IdentityProvider",
    "InMemoryAuthorizationVersions",
    "InMemoryReplayStore",
    "LoginStart",
    "LoginTransaction",
    "Mechanism",
    "Principal",
    "ProviderKind",
    "ReplayStore",
    "Requirement",
    "ResourcePolicy",
    "ScopeAuthorizer",
    "SessionInfo",
    "effective_permissions",
    "principal_from_claims",
    "requirement_for",
]
