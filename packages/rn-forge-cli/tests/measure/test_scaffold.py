"""Measure scaffold wheel builds and one installation."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import cast

import pytest

pytestmark = [
    pytest.mark.scaffold,
    pytest.mark.skipif(
        not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
    ),
]

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


def test_scaffold_setup(measure: Measure, request: pytest.FixtureRequest) -> None:
    with measure(
        "scaffold_setup", {"requirement": "rn-forge-cli"}, "tool startup"
    ) as counts:
        started = time.perf_counter()
        wheels = cast(dict[str, Path], request.getfixturevalue("built_wheels"))
        counts["build_wall_s"] = time.perf_counter() - started
        counts["builds"] = len(wheels)
        install = cast(Callable[..., Path], request.getfixturevalue("scaffold_venv"))
        started = time.perf_counter()
        executable_dir = install("rn-forge-cli")
        counts["install_wall_s"] = time.perf_counter() - started
        counts["installs"] = 1
        assert (executable_dir / "python").exists()
