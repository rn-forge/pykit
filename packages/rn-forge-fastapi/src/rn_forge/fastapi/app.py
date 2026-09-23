"""Construct FastAPI applications with the standard rn-forge adapters."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    get_global_response_propagator,
    set_global_response_propagator,  # pyright: ignore[reportUnknownVariableType]
)
from starlette.types import Lifespan

from rn_forge.fastapi.cors import CorsPolicy, apply_cors
from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.openapi import operation_id, repair_problem_schema
from rn_forge.fastapi.problem import Log, register_problem_handlers
from rn_forge.web import (
    API_CATALOG_PATH,
    LEGACY_LIVENESS_PATH,
    LINKSET_MEDIA_TYPE,
    LIVENESS_PATH,
    OPENAPI_PATH,
    READINESS_PATH,
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    Check,
    ProblemRegistry,
    api_catalog_body,
    default_registry,
)
from rn_forge.web.security import (
    API_SECURITY_HEADERS,
    HSTS_HEADER,
    SecurityHeadersMiddleware,
)

__all__ = ["AppConfig", "FastApiApp"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AppConfig:
    """The standard adapter configuration for :class:`FastApiApp`.

    Args:
        registry: Domain exception mappings. Register application exceptions
            before constructing this configuration.
        checks: Readiness checks, keyed by their wire-visible names.
        required_checks: Check names whose failure returns 503 from the
            readiness path.
        check_timeout: Maximum seconds a single readiness check may run.
        realm: Optional Bearer authentication realm for problem responses.
        tracing: Instrument the application with
            ``FastAPIInstrumentor.instrument_app`` and, when nothing else has,
            set a :class:`~opentelemetry.instrumentation.propagators.TraceResponsePropagator`
            as the global response propagator.
        log: Optional sink for server-error problem events and the
            ``request.complete`` access-log event.
        liveness_path: The liveness path.
        readiness_path: The readiness path.
        legacy_liveness_path: An alias of *liveness_path*, marked deprecated
            in the OpenAPI document. ``None`` serves no alias.
        max_body_bytes: The largest request body admitted, per RFC 9110
            §15.5.14. ``None`` disables the limit; uvicorn itself sets none.
        api_catalog: Serve RFC 9727's ``/.well-known/api-catalog``, pointing
            at the OpenAPI document and docs UI.
        security_headers: Install the OWASP REST Security Cheat Sheet response
            headers (``rn_forge.web.security.API_SECURITY_HEADERS``).
        hsts: Also add ``Strict-Transport-Security``. Off by default: sending
            it over plain HTTP tells a browser to refuse a future connection
            that isn't HTTPS, so it is opt-in for deployments that terminate
            TLS themselves rather than at a front end that already sets it.
        cors: A CORS policy to install, or ``None`` (the default) to install
            none — the application owns whether it has a CORS policy at all.
    """

    registry: ProblemRegistry = field(default_factory=default_registry)
    checks: Mapping[str, Check] = field(default_factory=dict[str, Check])
    required_checks: Collection[str] = ()
    check_timeout: float | None = 2.0
    realm: str | None = None
    tracing: bool = True
    log: Log | None = None
    liveness_path: str = LIVENESS_PATH
    readiness_path: str = READINESS_PATH
    legacy_liveness_path: str | None = LEGACY_LIVENESS_PATH
    max_body_bytes: int | None = 1_048_576
    api_catalog: bool = True
    security_headers: bool = True
    hsts: bool = False
    cors: CorsPolicy | None = None


class FastApiApp(FastAPI):
    """A :class:`fastapi.FastAPI` with the standard rn-forge wiring installed.

    FastAPI is inherited rather than wrapped, so ``@app.get()``,
    ``add_middleware`` and the full :class:`~fastapi.FastAPI` constructor
    keyword set remain available.
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        routers: Sequence[APIRouter] = (),
        lifespan: Lifespan[FastAPI] | None = None,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        **fastapi_kwargs: Any,
    ) -> None:
        """Initialize the application and install the standard adapters.

        Args:
            config: Standard adapter configuration. Defaults to
                ``AppConfig()``.
            routers: Application routers to include in order.
            lifespan: Application startup and shutdown hook.
            title: OpenAPI document title.
            description: OpenAPI document description.
            version: OpenAPI document version.
            **fastapi_kwargs: Forwarded to the :class:`fastapi.FastAPI`
                constructor. ``generate_unique_id_function`` defaults to
                :func:`operation_id` and may be overridden here.
        """
        resolved = config if config is not None else AppConfig()
        fastapi_kwargs.setdefault("generate_unique_id_function", operation_id)
        super().__init__(
            title=title,
            description=description,
            version=version,
            lifespan=lifespan,
            **fastapi_kwargs,
        )
        self.config = resolved
        if resolved.security_headers:
            headers = {**API_SECURITY_HEADERS, **(HSTS_HEADER if resolved.hsts else {})}
            self.add_middleware(SecurityHeadersMiddleware, headers=headers)
        if resolved.max_body_bytes is not None:
            self.add_middleware(
                BodySizeLimitMiddleware, max_bytes=resolved.max_body_bytes
            )
        if resolved.log is not None:
            self.add_middleware(AccessLogMiddleware, log=resolved.log)
        if resolved.cors is not None:
            apply_cors(self, resolved.cors)
        register_problem_handlers(
            self,
            registry=resolved.registry,
            realm=resolved.realm,
            log=resolved.log,
        )
        if resolved.tracing:
            FastAPIInstrumentor.instrument_app(self)
            if get_global_response_propagator() is None:
                # Process-global state, set only when nobody else set it.
                set_global_response_propagator(TraceResponsePropagator())
        self.include_router(
            health_router(
                checks=resolved.checks,
                required=resolved.required_checks,
                timeout=resolved.check_timeout,
                liveness_path=resolved.liveness_path,
                readiness_path=resolved.readiness_path,
                legacy_liveness_path=resolved.legacy_liveness_path,
            )
        )
        if resolved.api_catalog:
            self.add_api_route(
                API_CATALOG_PATH,
                self._api_catalog,
                methods=["GET", "HEAD"],
                include_in_schema=False,
            )
        for router in routers:
            self.include_router(router)

    async def _api_catalog(self) -> JSONResponse:
        """Serve RFC 9727's linkset, pointing at this app's own OpenAPI document and docs UI."""
        return JSONResponse(
            api_catalog_body(
                anchor="/",
                service_desc=self.openapi_url or OPENAPI_PATH,
                service_doc=self.docs_url,
                status=self.config.readiness_path,
            ),
            media_type=LINKSET_MEDIA_TYPE,
        )

    def openapi(self) -> dict[str, Any]:
        """Return the OpenAPI document, repaired for problem-response accuracy.

        Builds through ``super().openapi()`` — which caches the document the
        way plain :class:`~fastapi.FastAPI` does — and repairs the cached
        document exactly once. A consumer subclass adds further repairs by
        overriding this method and calling ``super().openapi()`` first.
        """
        if self.openapi_schema:
            return self.openapi_schema
        schema = super().openapi()
        self.openapi_schema = repair_problem_schema(
            schema, registry=self.config.registry
        )
        return self.openapi_schema
