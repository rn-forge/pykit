"""Opinionated rn-forge Django auth app."""

from rn_forge.django.auth.apps import AuthConfig
from rn_forge.django.auth.csrf import (
    CSRF_MIDDLEWARE,
    CSRF_SETTINGS,
    AuthCsrfMiddleware,
    enforce_csrf,
)
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
    "CSRF_MIDDLEWARE",
    "CSRF_SETTINGS",
    "SESSION_COOKIE",
    "SESSION_SETTINGS",
    "TRANSACTION_COOKIE",
    "ActiveSession",
    "AuthConfig",
    "AuthCsrfMiddleware",
    "AuthRoutesConfig",
    "CacheReplayStore",
    "CacheTransactionStore",
    "Sessions",
    "auth_urlpatterns",
    "enforce_csrf",
    "rotate_session",
]
