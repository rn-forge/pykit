"""Measure enabled and disabled application logging."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from io import StringIO

import pytest
from rn_forge.commons.logging import AppLogger

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

type Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("message", ["record %s", "record {}"])
def test_logging(measure: Measure, enabled: bool, message: str) -> None:
    factory = logging.getLogRecordFactory()
    logger_class = logging.getLoggerClass()
    AppLogger.get_logger("measurement.registration")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = AppLogger("measurement", logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    logger.disabled = not enabled
    try:
        case = "logging_enabled" if enabled else "logging_disabled"
        if message == "record {}":
            case += "_brace"
        with measure(
            case,
            {"records": 10_000, "enabled": enabled, "message": message},
            "cpu",
        ) as counts:
            for index in range(10_000):
                logger.info(message, index)
            counts["attempted_records"] = 10_000
            counts["records"] = len(stream.getvalue().splitlines())
            assert counts["records"] == (10_000 if enabled else 0)
    finally:
        logger.removeHandler(handler)
        handler.close()
        logging.setLogRecordFactory(factory)
        logging.setLoggerClass(logger_class)
