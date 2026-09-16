"""Build ``/healthz`` liveness and ``/readyz`` readiness routes."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from rn_forge.fastapi.schemas import HealthReport
from rn_forge.web import Check, run_checks

__all__ = ["health_router"]


def health_router(
    *,
    checks: Mapping[str, Check],
    required: Collection[str] = (),
    prefix: str = "",
    timeout: float | None = None,
) -> APIRouter:
    """Return a router serving ``/healthz`` and ``/readyz``.

    Args:
        checks: Name → check, sync or async, returning a
            :class:`rn_forge.web.CheckResult` or a ``bool``. A check that raises
            is reported as ``fail``; it never fails the endpoint.
        required: The names whose failure makes the service unavailable (503).
        prefix: Mounted in front of both paths.
        timeout: Seconds each check may run before it is reported as ``fail``,
            so a hung dependency cannot hang ``/readyz``. ``None`` waits
            indefinitely.
    """
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "pass"}

    @router.get(
        "/readyz",
        response_model=HealthReport,
        responses={
            503: {"model": HealthReport, "description": "A required check failed"}
        },
    )
    async def readyz() -> JSONResponse:
        report = await run_checks(checks, required=required, timeout=timeout)
        return JSONResponse(report.as_body(), status_code=report.http_status)

    return router
