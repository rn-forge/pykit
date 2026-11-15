"""Measure cold logging imports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]

_COLD = """
import json
import resource
import sys
import rn_forge.commons.logging
print(json.dumps({"ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "imports": len(sys.modules)}))
"""


def test_cold_logging_import(measure: Measure) -> None:
    with measure("logging_cold_import", {"processes": 1}, "tool startup") as counts:
        result = subprocess.run(
            [sys.executable, "-c", _COLD], capture_output=True, text=True, check=True
        )
        child = json.loads(result.stdout.splitlines()[-1])
        counts["child_peak_bytes"] = child["ru_maxrss"] * (
            1 if sys.platform == "darwin" else 1024
        )
        counts["imports"] = child["imports"]
