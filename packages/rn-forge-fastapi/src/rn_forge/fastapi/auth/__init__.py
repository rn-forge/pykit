"""FastAPI authentication: security dependencies and the ``/auth`` router."""

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
    "SESSION_COOKIE",
    "TRANSACTION_COOKIE",
    "ActiveSession",
    "AuthRoutesConfig",
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
