"""Check the measurement record and opt-in marker."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


def test_measure_contract(
    measure: Measure,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    cases = [
        item
        for item in request.session.items
        if item.path.parent == Path(__file__).parent and item.path != Path(__file__)
    ]
    assert cases
    for item in cases:
        marker = item.get_closest_marker("skipif")
        assert marker is not None
        assert marker.args == (not bool(os.environ.get("PYKIT_MEASURE_OUT")),)

    monkeypatch.setenv("PYKIT_MEASURE_OUT", str(tmp_path))
    with measure("contract", {"operations": 1}, "cpu") as counts:
        counts["operations"] = 1
    lines = (tmp_path / "results.jsonl").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {
        "case",
        "commit",
        "python",
        "platform",
        "inputs",
        "wall_s",
        "peak_bytes",
        "counts",
        "kind",
    }
    assert record["case"] == "contract"
    assert len(record["commit"]) == 40
    assert record["python"]
    assert record["platform"]
    assert record["inputs"] == {"operations": 1}
    assert record["wall_s"] > 0
    assert record["peak_bytes"] >= 0
    assert record["counts"] == {"operations": 1}
    assert record["kind"] == "cpu"
