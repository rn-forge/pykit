"""Measure command help and CLI import startup."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from rn_forge.cli import CliApp, run

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
from rn_forge.cli import CliApp, run
app = CliApp("measure", "Measurement app.")
@app.command()
def hello() -> None:
    pass
assert run(app, ["--help"]) == 0
print(json.dumps({"ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "imports": len(sys.modules)}))
"""


def test_cold_help(measure: Measure) -> None:
    with measure("cli_cold_help", {"processes": 1}, "tool startup") as counts:
        result = subprocess.run(
            [sys.executable, "-c", _COLD], capture_output=True, text=True, check=True
        )
        child = json.loads(result.stdout.splitlines()[-1])
        counts["child_peak_bytes"] = child["ru_maxrss"] * (
            1 if sys.platform == "darwin" else 1024
        )
        counts["imports"] = child["imports"]


def test_warm_help(measure: Measure) -> None:
    app = CliApp("measure", "Measurement app.")

    @app.command()
    def hello() -> None:
        pass

    assert run(app, ["--help"]) == 0
    with measure(
        "cli_warm_help", {"calls": 1, "warmup_calls": 1}, "tool startup"
    ) as counts:
        assert run(app, ["--help"]) == 0
        counts["calls"] = 1
        counts["imports"] = len(sys.modules)


def test_import_time(measure: Measure) -> None:
    with measure("cli_import", {"processes": 1}, "tool startup") as counts:
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "importtime",
                "-c",
                "import rn_forge.cli; import resource; print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        counts["imports"] = sum(
            line.startswith("import time:") and "|" in line and "self [us]" not in line
            for line in result.stderr.splitlines()
        )
        counts["child_peak_bytes"] = int(result.stdout.strip()) * (
            1 if sys.platform == "darwin" else 1024
        )
