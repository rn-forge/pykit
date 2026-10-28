"""Authentication primitives.

The OIDC adapter, :mod:`rn_forge.auth.oidc`, and the Redis adapter,
:mod:`rn_forge.auth.redis`, need the ``oidc`` and ``redis`` extras and are
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
from rn_forge.auth.flow import CompletedLogin, LoginFailed, LoginFlow
from rn_forge.auth.identity import (
    ExternalIdentity,
    IdentityProvider,
    LoginRequest,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)
from rn_forge.auth.local import (
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    DevelopmentModeRequired,
    PasswordIdentityProvider,
    PasswordVerifier,
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
from rn_forge.auth.redirects import InvalidReturnTo, validate_return_to
from rn_forge.auth.session_body import CALLBACK_ERRORS, CallbackError, SessionBody
from rn_forge.auth.stores import (
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    ReplayStore,
    SessionStore,
    TransactionStore,
)

__all__ = [
    "CALLBACK_ERRORS",
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
    "CallbackError",
    "CompletedLogin",
    "DevelopmentAccount",
    "DevelopmentIdentityProvider",
    "DevelopmentModeRequired",
    "ExternalIdentity",
    "IdentityProvider",
    "InMemoryAuthorizationVersions",
    "InMemoryReplayStore",
    "InMemorySessionStore",
    "InMemoryTransactionStore",
    "InvalidReturnTo",
    "LoginFailed",
    "LoginFlow",
    "LoginRequest",
    "LoginStart",
    "LoginTransaction",
    "Mechanism",
    "PasswordIdentityProvider",
    "PasswordVerifier",
    "Principal",
    "ProviderKind",
    "ReplayStore",
    "Requirement",
    "ResourcePolicy",
    "ScopeAuthorizer",
    "SessionBody",
    "SessionInfo",
    "SessionStore",
    "TransactionStore",
    "effective_permissions",
    "principal_from_claims",
    "requirement_for",
    "validate_return_to",
]
