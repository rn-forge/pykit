"""Measure XLSX serialization and workbook loading."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from io import BytesIO

import pytest

pytest.importorskip("openpyxl")
import tablib
from rn_forge.data.excel import ExcelUtils, write_xlsx

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


def test_excel(measure: Measure) -> None:
    with measure(
        "excel_roundtrip", {"rows": 50_000, "columns": 10}, "buffering"
    ) as counts:
        dataset = tablib.Dataset(headers=[f"column{i}" for i in range(10)])
        for index in range(50_000):
            dataset.append([index * 10 + column for column in range(10)])
        content = write_xlsx(dataset)
        workbook = ExcelUtils.load_workbook(BytesIO(content))
        try:
            sheet = workbook.active
            assert sheet is not None
            assert sheet.max_row == 50_001
            assert sheet.max_column == 10
            counts["bytes"] = len(content)
            counts["rows"] = 50_000
            counts["cells"] = 500_000
        finally:
            workbook.close()
