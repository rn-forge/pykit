"""FastAPI authentication: security dependencies and the ``/auth`` router."""

from rn_forge.fastapi.auth.csrf import (
    ANONYMOUS_PREFIX,
    ANONYMOUS_TTL,
    CSRF_COOKIE,
    CSRF_HEADER,
    CsrfProtection,
    CsrfStore,
    InMemoryCsrfStore,
)
from rn_forge.fastapi.auth.dependencies import basic_auth, bearer_auth, requires
from rn_forge.fastapi.auth.routes import (
    TRANSACTION_COOKIE,
    AuthRoutesConfig,
    auth_router,
    sessions_for,
)
from rn_forge.fastapi.auth.sessions import (
    SESSION_COOKIE,
    ActiveSession,
    SessionMiddleware,
    Sessions,
    active_session,
    rotate_session,
)

__all__ = [
    "ANONYMOUS_PREFIX",
    "ANONYMOUS_TTL",
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "SESSION_COOKIE",
    "TRANSACTION_COOKIE",
    "ActiveSession",
    "AuthRoutesConfig",
    "CsrfProtection",
    "CsrfStore",
    "InMemoryCsrfStore",
    "SessionMiddleware",
    "Sessions",
    "active_session",
    "auth_router",
    "basic_auth",
    "bearer_auth",
    "requires",
    "rotate_session",
    "sessions_for",
]
