"""Readiness checks: run a map of them, aggregate, and decide the HTTP status.

A readiness endpoint answers one question — should a load balancer send this
process traffic? — and it answers it by running a named check per dependency.
This module runs the checks; the endpoints themselves are each framework
package's job, because a Django view and a FastAPI router share no shape.

Also not here: liveness. ``/healthz`` returns 200 unconditionally and needs no
library.

Four statuses, not a bool
-------------------------

``pass``/``warn``/``fail`` are obvious. ``skipped`` is the one nobody invents on
their own and the one that matters: a check group that is configured away or
not yet implemented reports ``skipped`` with a reason, so its absence is
*visible* rather than silent. It costs nothing and it is the difference between
"the queue check passed" and "there is no queue check".

The rules that make this safe
-----------------------------

- **A check may return a bare ``bool``** and it is coerced. A one-line
  ``lambda: db_reachable()`` should not have to build a :class:`CheckResult`.
- **Every check is wrapped.** A check that raises becomes ``fail`` with
  ``reason=str(exc)``. A check reports a failure; it must never itself crash
  the run, because a readiness endpoint that 500s tells a load balancer
  nothing.
- **``required`` drives the HTTP status, and nothing else does.** A ``fail`` in
  *required* → 503. A ``fail`` outside it degrades the overall status but
  leaves ``http_status`` at 200. ``warn`` never changes ``http_status``. The
  report carries ``http_status`` so each framework does not re-derive it.
- **The async runner runs checks concurrently.** A readiness endpoint that
  serially awaits five two-second timeouts is a ten-second readiness endpoint.
- **The async runner can bound each check.** With ``timeout`` set, a check
  still running after that many seconds is reported as ``fail`` and the run
  moves on — a hung dependency must not hang the probe that exists to report
  it. An async check is cancelled; a sync check's worker thread cannot be, so
  it finishes in the background and its result is discarded.
- **The sync runner refuses an awaitable** rather than reporting a coroutine
  object as truthy-and-therefore-passing, which is precisely the bug that
  would otherwise ship.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import WebError

__all__ = [
    "Check",
    "CheckResult",
    "CheckStatus",
    "HealthReport",
    "run_checks",
    "run_checks_sync",
]

type CheckStatus = Literal["pass", "warn", "fail", "skipped"]
"""The four outcomes a single check may report."""


@dataclass(frozen=True)
class CheckResult(DataclassMixin):
    """One dependency's verdict.

    ``remediation`` is what an operator should *do* about a failure, which is
    the field that turns a readiness page into a runbook.
    """

    status: CheckStatus
    reason: str | None = None
    remediation: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict[str, Any])


type Check = Callable[[], CheckResult | bool | Awaitable[CheckResult | bool]]
"""A named check: a zero-argument callable, sync or async, returning a result or a bool."""


@dataclass(frozen=True)
class HealthReport(DataclassMixin):
    """The aggregate of one readiness run."""

    status: CheckStatus
    checks: Mapping[str, CheckResult]
    http_status: int

    def as_body(self) -> dict[str, Any]:
        """Return the wire body: ``status`` and ``checks``, and nothing else.

        ``http_status`` is deliberately **not** in the body. It exists so each
        framework does not re-derive the status code from the checks, and a
        status line repeated as a body field is one more thing that can
        disagree with itself. It is also the only snake_case name on this
        dataclass, so leaving it out is what keeps the response camelCase
        without a per-field alias.
        """
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


def run_checks_sync(
    checks: Mapping[str, Check], *, required: Collection[str] = ()
) -> HealthReport:
    """Run *checks* sequentially and aggregate them.

    Args:
        checks: Name → check. Every check must be synchronous.
        required: Names whose failure makes the service unavailable (503).

    Returns:
        The aggregate report, including the HTTP status to serve.

    Raises:
        WebError: A check returned an awaitable. This is raised rather than
            swallowed into a ``fail``, because it is a wiring mistake in the
            caller's code, not a sick dependency — and reporting it as a
            failing check would hide it behind a red dependency.
    """
    results: dict[str, CheckResult] = {}
    for name, check in checks.items():
        try:
            outcome = check()
        except Exception as exc:  # noqa: BLE001 - a check must never crash the run
            results[name] = _failed(exc)
            continue
        if inspect.isawaitable(outcome):
            if inspect.iscoroutine(outcome):
                # Close it, or the "coroutine was never awaited" warning lands
                # on an unrelated line whenever the GC gets round to it.
                outcome.close()
            raise WebError(
                "Health check {!r} is asynchronous; use run_checks() instead", name
            )
        results[name] = _coerce(outcome)
    return _aggregate(results, required)
