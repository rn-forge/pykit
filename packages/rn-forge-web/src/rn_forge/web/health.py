"""Run and aggregate readiness checks.

Exceptions and timeouts become failed checks. A failed required check makes
the service unavailable; optional failures only degrade the aggregate status.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Collection, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from rn_forge.commons.lang.dataclasses import LenientDataclassMixin
from rn_forge.web.exceptions import WebError

__all__ = [
    "LEGACY_LIVENESS_PATH",
    "LIVENESS_PATH",
    "READINESS_PATH",
    "Check",
    "CheckResult",
    "CheckStatus",
    "HealthReport",
    "liveness_body",
    "run_checks",
    "run_checks_sync",
]

LIVENESS_PATH: Final = "/livez"
"""Default liveness path (kubernetes.io "Kubernetes API health endpoints")."""

READINESS_PATH: Final = "/readyz"
"""Default readiness path."""

LEGACY_LIVENESS_PATH: Final = "/healthz"
"""Deprecated alias of :data:`LIVENESS_PATH`, kept for hosts still probing it."""

type CheckStatus = Literal["pass", "warn", "fail", "skipped"]
"""The four outcomes a single check may report."""


@dataclass(frozen=True)
class CheckResult(LenientDataclassMixin):
    """One dependency's verdict.

    Lenient parsing is required because dacite cannot type-check the PEP 695
    :data:`CheckStatus` alias.
    """

    status: CheckStatus
    reason: str | None = None
    remediation: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict[str, Any])


type Check = Callable[[], CheckResult | bool | Awaitable[CheckResult | bool]]
"""A named check: a zero-argument callable, sync or async, returning a result or a bool."""


@dataclass(frozen=True)
class HealthReport(LenientDataclassMixin):
    """The aggregate of one readiness run.

    Lenient parsing is required because dacite cannot type-check the PEP 695
    :data:`CheckStatus` alias.
    """

    status: CheckStatus
    checks: Mapping[str, CheckResult]
    http_status: int

    def as_body(self) -> dict[str, Any]:
        """Return ``status`` and ``checks`` without the transport status."""
        return {
            "status": self.status,
            "checks": {
                name: {
                    "status": result.status,
                    "reason": result.reason,
                    "remediation": result.remediation,
                    "details": dict(result.details),
                }
                for name, result in self.checks.items()
            },
        }


def liveness_body() -> dict[str, str]:
    """Return the liveness body: ``{"status": "pass"}``, served with 200.

    Liveness runs no checks: it answers whether the process can serve a
    request at all.
    """
    return {"status": "pass"}


_OK: Final = 200
_UNAVAILABLE: Final = 503

# Worst-wins ordering for the aggregate status. `skipped` is deliberately the
# weakest: a skipped check is recorded and reported but never degrades the
# overall verdict, because "not configured" is not "broken".
_SEVERITY: Final[dict[CheckStatus, int]] = {
    "skipped": 0,
    "pass": 1,
    "warn": 2,
    "fail": 3,
}


def _coerce(value: CheckResult | bool) -> CheckResult:
    """Turn a check's return value into a :class:`CheckResult`."""
    if isinstance(value, CheckResult):
        return value
    return CheckResult(status="pass" if value else "fail")


def _failed(exc: BaseException) -> CheckResult:
    """Turn a raising check into a ``fail`` carrying its message."""
    return CheckResult(status="fail", reason=str(exc) or type(exc).__name__)


def _aggregate(
    results: Mapping[str, CheckResult], required: Collection[str]
) -> HealthReport:
    """Combine per-check results into a report, applying the *required* rule."""
    overall: CheckStatus = "pass"
    for result in results.values():
        if _SEVERITY[result.status] > _SEVERITY[overall]:
            overall = result.status
    if not results:
        overall = "pass"
    unavailable = any(
        results[name].status == "fail" for name in required if name in results
    )
    return HealthReport(
        status=overall,
        checks=results,
        http_status=_UNAVAILABLE if unavailable else _OK,
    )


async def _run_one(check: Check) -> CheckResult:
    """Run one check, awaiting an awaitable result and never propagating.

    A synchronous check runs in a worker thread, so blocking I/O in it neither
    stalls the event loop nor serialises the other checks.
    """
    try:
        if inspect.iscoroutinefunction(check):
            outcome = check()
        else:
            outcome = await asyncio.to_thread(check)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return _coerce(outcome)
    except Exception as exc:  # noqa: BLE001 - a check must never crash the run
        return _failed(exc)


async def _run_bounded(check: Check, timeout: float | None) -> CheckResult:
    """Run one check, failing it if it is still running after *timeout* seconds."""
    if timeout is None:
        return await _run_one(check)
    try:
        return await asyncio.wait_for(_run_one(check), timeout)
    except TimeoutError:
        return CheckResult(status="fail", reason=f"timed out after {timeout:g}s")


async def run_checks(
    checks: Mapping[str, Check],
    *,
    required: Collection[str] = (),
    timeout: float | None = None,
) -> HealthReport:
    """Run *checks* concurrently and aggregate them.

    Args:
        checks: Name → check. Sync and async checks may be mixed freely.
        required: Names whose failure makes the service unavailable (503).
            A name not present in *checks* is ignored.
        timeout: Seconds each check may run before it is reported as
            ``fail``. ``None`` (the default) waits indefinitely.

    Returns:
        The aggregate report, including the HTTP status to serve.
    """
    names = list(checks)
    results = await asyncio.gather(
        *(_run_bounded(checks[name], timeout) for name in names)
    )
    return _aggregate(dict(zip(names, results, strict=True)), required)


def _run_one_sync(check: Check) -> CheckResult:
    """Run one synchronous check, mirroring :func:`_run_one`'s error handling.

    Raises:
        WebError: The check returned an awaitable.
    """
    try:
        outcome = check()
    except Exception as exc:  # noqa: BLE001 - a check must never crash the run
        return _failed(exc)
    if inspect.isawaitable(outcome):
        if inspect.iscoroutine(outcome):
            # Close it, or the "coroutine was never awaited" warning lands on
            # an unrelated line whenever the GC gets round to it.
            outcome.close()
        raise WebError("Health check is asynchronous; use run_checks() instead")
    return _coerce(outcome)


def run_checks_sync(
    checks: Mapping[str, Check],
    *,
    required: Collection[str] = (),
    timeout: float | None = None,
) -> HealthReport:
    """Run *checks* concurrently in a thread pool and aggregate them.

    Args:
        checks: Name → check. Every check must be synchronous.
        required: Names whose failure makes the service unavailable (503).
        timeout: Seconds each check may run before it is reported as
            ``fail``. ``None`` (the default) waits indefinitely.

    Returns:
        The aggregate report, including the HTTP status to serve.

    Raises:
        WebError: A check returned an awaitable. This is raised rather than
            swallowed into a ``fail``, because it is a wiring mistake in the
            caller's code, not a sick dependency — and reporting it as a
            failing check would hide it behind a red dependency.
    """
    names = list(checks)
    results: dict[str, CheckResult] = {}
    with ThreadPoolExecutor(max_workers=len(names) or 1) as executor:
        futures = {name: executor.submit(_run_one_sync, checks[name]) for name in names}
        for name in names:
            try:
                results[name] = futures[name].result(timeout=timeout)
            except TimeoutError:
                results[name] = CheckResult(
                    status="fail", reason=f"timed out after {timeout:g}s"
                )
    return _aggregate(results, required)
