"""Build liveness and readiness routes."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from rn_forge.web import (
    HealthReport,
    LEGACY_LIVENESS_PATH,
    LIVENESS_PATH,
    READINESS_PATH,
    Check,
    liveness_body,
    run_checks,
)

__all__ = ["health_router"]


def health_router(
    *,
    checks: Mapping[str, Check],
    required: Collection[str] = (),
    prefix: str = "",
    timeout: float | None = None,
    liveness_path: str = LIVENESS_PATH,
    readiness_path: str = READINESS_PATH,
    legacy_liveness_path: str | None = LEGACY_LIVENESS_PATH,
) -> APIRouter:
    """Return a router serving the liveness and readiness paths.

    Args:
        checks: Name → check, sync or async, returning a
            :class:`rn_forge.web.CheckResult` or a ``bool``. A check that raises
            is reported as ``fail``; it never fails the endpoint.
        required: The names whose failure makes the service unavailable (503).
        prefix: Mounted in front of every path.
        timeout: Seconds each check may run before it is reported as ``fail``,
            so a hung dependency cannot hang the readiness path. ``None``
            waits indefinitely.
        liveness_path: The liveness path.
        readiness_path: The readiness path.
        legacy_liveness_path: An alias of *liveness_path*, marked deprecated
            in the OpenAPI document. ``None`` serves no alias.
    """
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get(liveness_path)
    async def livez() -> dict[str, str]:
        return liveness_body()

    if legacy_liveness_path is not None:

        @router.get(legacy_liveness_path, deprecated=True)
        async def healthz() -> dict[str, str]:
            return liveness_body()

    @router.get(
        readiness_path,
        response_model=HealthReport,
        responses={
            503: {"model": HealthReport, "description": "A required check failed"}
        },
    )
    async def readyz() -> JSONResponse:
        report = await run_checks(checks, required=required, timeout=timeout)
        return JSONResponse(report.as_body(), status_code=report.http_status)

    return router
