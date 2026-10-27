"""Authentication primitives.

The OIDC adapter, :mod:`rn_forge.auth.oidc`, needs the ``oidc`` extra and is
imported directly.
"""

from rn_forge.auth.authorization import (
    AsyncAuthenticator,
    Authenticator,
    Authorizer,
    ScopeAuthorizer,
)
from rn_forge.auth.principal import Principal, Requirement, principal_from_claims

__all__ = [
    "AsyncAuthenticator",
    "Authenticator",
    "Authorizer",
    "Principal",
    "Requirement",
    "ScopeAuthorizer",
    "principal_from_claims",
]
