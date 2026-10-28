"""FastAPI adapters for :mod:`rn_forge.web` contracts."""

from rn_forge.fastapi.app import AppConfig, FastApiApp
from rn_forge.fastapi.auth import (
    ANONYMOUS_PREFIX,
    ANONYMOUS_TTL,
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    TRANSACTION_COOKIE,
    ActiveSession,
    AuthRoutesConfig,
    BearerAuth,
    CsrfProtection,
    CsrfStore,
    InMemoryCsrfStore,
    PolicyGuard,
    SessionMiddleware,
    Sessions,
    active_session,
    auth_router,
    basic_auth,
    bearer_auth,
    current_principal,
    requires,
    requires_permission,
    rotate_session,
    sessions_for,
)
from rn_forge.fastapi.cors import CorsPolicy, apply_cors
from rn_forge.fastapi.dependencies import (
    conditional_get,
    order_by_param,
    page_params,
    require_idempotency_key,
    require_if_match,
)
from rn_forge.fastapi.deprecation import deprecated
from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.idempotency import idempotent
from rn_forge.fastapi.merge_patch import (
    merge_into,
    merge_patch_body,
    merge_patch_openapi,
)
from rn_forge.fastapi.openapi import operation_id
from rn_forge.fastapi.problem import Log, register_problem_handlers
from rn_forge.fastapi.read_mask import masked, read_mask_param
from rn_forge.fastapi.soft_delete import (
    SoftDeleteState,
    SoftDeleteStore,
    show_deleted_param,
    soft_delete_router,
)

__all__ = [
    "ANONYMOUS_PREFIX",
    "ANONYMOUS_TTL",
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "SESSION_COOKIE",
    "TRANSACTION_COOKIE",
    "ActiveSession",
    "AppConfig",
    "AuthRoutesConfig",
    "BearerAuth",
    "CorsPolicy",
    "CsrfProtection",
    "CsrfStore",
    "FastApiApp",
    "InMemoryCsrfStore",
    "Log",
    "PolicyGuard",
    "SessionMiddleware",
    "Sessions",
    "SoftDeleteState",
    "SoftDeleteStore",
    "active_session",
    "apply_cors",
    "auth_router",
    "basic_auth",
    "bearer_auth",
    "conditional_get",
    "current_principal",
    "deprecated",
    "health_router",
    "idempotent",
    "masked",
    "merge_into",
    "merge_patch_body",
    "merge_patch_openapi",
    "operation_id",
    "order_by_param",
    "page_params",
    "read_mask_param",
    "register_problem_handlers",
    "require_idempotency_key",
    "require_if_match",
    "requires",
    "requires_permission",
    "rotate_session",
    "sessions_for",
    "show_deleted_param",
    "soft_delete_router",
]
