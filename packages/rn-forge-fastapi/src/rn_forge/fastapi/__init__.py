"""FastAPI adapters for :mod:`rn_forge.web` contracts."""

from rn_forge.fastapi.app import AppConfig, FastApiApp
from rn_forge.fastapi.auth import basic_auth, bearer_auth, requires
from rn_forge.fastapi.cors import CorsPolicy, apply_cors
from rn_forge.fastapi.dependencies import (
    conditional_get,
    page_params,
    require_idempotency_key,
    require_if_match,
)
from rn_forge.fastapi.deprecation import deprecated
from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.idempotency import idempotent
from rn_forge.fastapi.openapi import operation_id
from rn_forge.fastapi.problem import Log, register_problem_handlers

__all__ = [
    "AppConfig",
    "CorsPolicy",
    "FastApiApp",
    "Log",
    "apply_cors",
    "basic_auth",
    "bearer_auth",
    "conditional_get",
    "deprecated",
    "health_router",
    "idempotent",
    "operation_id",
    "page_params",
    "register_problem_handlers",
    "require_idempotency_key",
    "require_if_match",
    "requires",
]
