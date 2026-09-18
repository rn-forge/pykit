"""FastAPI adapters for :mod:`rn_forge.web` contracts."""

from rn_forge.fastapi.app import AppConfig, create_app
from rn_forge.fastapi.auth import basic_auth, bearer_auth, requires
from rn_forge.fastapi.dependencies import (
    page_params,
    require_idempotency_key,
    require_if_match,
)
from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.openapi import (
    OPENAPI_VERSION,
    install_problem_schema,
    operation_id,
)
from rn_forge.fastapi.problem import Log, register_problem_handlers
from rn_forge.fastapi.schemas import (
    CheckResult,
    HealthReport,
    Page,
    ProblemDetail,
    WireModel,
)

__all__ = [
    "OPENAPI_VERSION",
    "AppConfig",
    "CheckResult",
    "HealthReport",
    "Log",
    "Page",
    "ProblemDetail",
    "WireModel",
    "basic_auth",
    "bearer_auth",
    "create_app",
    "health_router",
    "install_problem_schema",
    "operation_id",
    "page_params",
    "register_problem_handlers",
    "require_idempotency_key",
    "require_if_match",
    "requires",
]
