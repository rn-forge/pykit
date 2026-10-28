"""Opinionated rn-forge Django auth app."""

from rn_forge.django.auth.apps import AuthConfig
from rn_forge.django.auth.routes import (
    TRANSACTION_COOKIE,
    AuthRoutesConfig,
    auth_urlpatterns,
)
from rn_forge.django.auth.sessions import (
    SESSION_COOKIE,
    SESSION_SETTINGS,
    ActiveSession,
    Sessions,
    rotate_session,
)
from rn_forge.django.auth.stores import CacheReplayStore, CacheTransactionStore

__all__ = [
    "SESSION_COOKIE",
    "SESSION_SETTINGS",
    "TRANSACTION_COOKIE",
    "ActiveSession",
    "AuthConfig",
    "AuthRoutesConfig",
    "CacheReplayStore",
    "CacheTransactionStore",
    "Sessions",
    "auth_urlpatterns",
    "rotate_session",
]
