"""Measure synchronous readiness checks."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from rn_forge.web.health import run_checks_sync

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


@pytest.mark.parametrize("timeout", [None, 1.0])
def test_readiness(measure: Measure, timeout: float | None) -> None:
    def check() -> bool:
        time.sleep(0.2)
        return True

    with measure(
        "readiness_timeout" if timeout else "readiness_unbounded",
        {"checks": 8, "sleep_s": 0.2, "timeout_s": timeout},
        "io",
    ) as counts:
        report = run_checks_sync({str(i): check for i in range(8)}, timeout=timeout)
        counts["checks"] = len(report.checks)
        counts["sum_sleeps_s"] = 8 * 0.2
        assert report.status == "pass"
