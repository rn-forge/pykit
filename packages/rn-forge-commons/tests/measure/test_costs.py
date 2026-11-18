"""Measure file hashing, task submission and nested dictionary merging."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.lang.collections import DictUtils
from rn_forge.commons.runtime.tasks import Task, TaskPool

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]

_CHUNK_SIZE = 1024 * 1024


class _MeasurementTask(Task):
    """Task with no work beyond pool submission."""

    def run(self) -> None:
        pass


@pytest.mark.parametrize("size_mib", [8, 64, 256])
def test_file_digest(measure: Measure, tmp_path: Path, size_mib: int) -> None:
    path = tmp_path / f"{size_mib}mib.bin"
    chunk = b"x" * _CHUNK_SIZE
    with path.open("wb") as stream:
        for _ in range(size_mib):
            stream.write(chunk)

    with measure("file_digest", {"size_mib": size_mib}, "io") as counts:
        result = ContentHash.of_file(path)
        assert result is not None
        counts["bytes"] = size_mib * _CHUNK_SIZE


@pytest.mark.parametrize("size", [1_000, 4_000, 16_000])
def test_task_duplicate_check(measure: Measure, size: int) -> None:
    tasks = [_MeasurementTask(f"task-{index}") for index in range(size)]
    pool = TaskPool[_MeasurementTask](max_workers=1)
    try:
        with measure("task_duplicate_check", {"size": size}, "cpu") as counts:
            pool.submit(*tasks)
            counts["names"] = size
    finally:
        pool.shutdown()


def _tree(depth: int, fanout: int) -> dict[str, Any]:
    if depth == 1:
        return {f"key-{index}": 1 for index in range(fanout)}
    return {f"key-{index}": _tree(depth - 1, fanout) for index in range(fanout)}


@pytest.mark.parametrize("target_kind", ["empty", "equal"])
def test_dict_merge(measure: Measure, target_kind: str) -> None:
    depth = 8
    fanout = 4
    override = _tree(depth, fanout)
    target = {} if target_kind == "empty" else _tree(depth, fanout)

    with measure(
        "dict_merge",
        {"depth": depth, "fanout": fanout, "target": target_kind},
        "cpu",
    ) as counts:
        DictUtils.merge(target, override)
        counts["leaves"] = fanout**depth
