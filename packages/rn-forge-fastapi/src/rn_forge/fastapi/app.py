"""Construct FastAPI applications with the standard rn-forge adapters."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI
from starlette.types import Lifespan

from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.openapi import install_problem_schema, operation_id
from rn_forge.fastapi.problem import Log, register_problem_handlers
from rn_forge.web import (
    DEFAULT_CORRELATION_HEADER,
    Check,
    CorrelationIdMiddleware,
    ProblemRegistry,
    default_registry,
)

__all__ = ["AppConfig", "create_app"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AppConfig:
    """The standard adapter configuration for :func:`create_app`.

    Args:
        registry: Domain exception mappings. Register application exceptions
            before constructing this configuration.
        checks: Readiness checks, keyed by their wire-visible names.
        required_checks: Check names whose failure returns 503 from ``/readyz``.
        check_timeout: Maximum seconds a single readiness check may run.
        realm: Optional Bearer authentication realm for problem responses.
        correlation_header: The correlation request and response header name.
        log: Optional sink for server-error problem events.
    """

    registry: ProblemRegistry = field(default_factory=default_registry)
    checks: Mapping[str, Check] = field(default_factory=dict[str, Check])
    required_checks: Collection[str] = ()
    check_timeout: float | None = None
    realm: str | None = None
    correlation_header: str = DEFAULT_CORRELATION_HEADER
    log: Log | None = None


def create_app(
    config: AppConfig,
    *,
    routers: Sequence[APIRouter] = (),
    lifespan: Lifespan[FastAPI] | None = None,
    title: str = "FastAPI",
    description: str = "",
    version: str = "0.1.0",
) -> FastAPI:
    """Return a FastAPI application with the standard rn-forge wiring.

    Args:
        config: Standard adapter configuration.
        routers: Application routers to include in order.
        lifespan: Application startup and shutdown hook.
        title: OpenAPI document title.
        description: OpenAPI document description.
        version: OpenAPI document version.

    Returns:
        A normal :class:`fastapi.FastAPI` instance. Add routes, dependencies,
        middleware, and framework configuration through its usual APIs.
    """
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        generate_unique_id_function=operation_id,
    )
    app.add_middleware(CorrelationIdMiddleware, header_name=config.correlation_header)
    register_problem_handlers(
        app,
        registry=config.registry,
        realm=config.realm,
        correlation_header=config.correlation_header,
        log=config.log,
    )
    install_problem_schema(app, registry=config.registry)
    app.include_router(
        health_router(
            checks=config.checks,
            required=config.required_checks,
            timeout=config.check_timeout,
        )
    )
    for router in routers:
        app.include_router(router)
    return app
