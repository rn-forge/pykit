"""Record opt-in workload measurements as JSON Lines."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import tracemalloc
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import pytest

type Counts = dict[str, int | float]
type Measure = Callable[[str, dict[str, object], str], AbstractContextManager[Counts]]


@pytest.fixture
def measure() -> Measure:
    @contextmanager
    def record(case: str, inputs: dict[str, object], kind: str) -> Iterator[Counts]:
        out = Path(os.environ["PYKIT_MEASURE_OUT"])
        out.mkdir(parents=True, exist_ok=True)
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        counts: Counts = {}
        tracemalloc.start()
        started = time.perf_counter()
        try:
            yield counts
        finally:
            wall_s = time.perf_counter() - started
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            with (out / "results.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "case": case,
                            "commit": commit,
                            "python": platform.python_version(),
                            "platform": platform.platform(),
                            "inputs": inputs,
                            "wall_s": wall_s,
                            "peak_bytes": peak_bytes,
                            "counts": counts,
                            "kind": kind,
                        }
                    )
                    + "\n"
                )

    return record
