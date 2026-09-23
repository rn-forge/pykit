"""Tests for rn_forge.commons.logging.structlog."""

from __future__ import annotations

import logging
import sys

import pytest

pytest.importorskip("structlog")

from rn_forge.commons.logging import TRACE, AppLogger  # noqa: E402
from rn_forge.commons.logging.structlog import StructLogger, otel_processor  # noqa: E402


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture(autouse=True)
def reset_logger_state():
    AppLogger._configured = False
    yield
    AppLogger._configured = False
    logging.getLogger().handlers.clear()


def _configure(*, level: int = TRACE) -> None:
    AppLogger._configured = False
    AppLogger.initialize(
        root_logger_name="structlog_test", level=level, force_reconfigure=True
    )


class TestCustomLevels:
    @pytest.mark.parametrize(
        ("method", "expected_level"),
        [
            ("trace", AppLogger.TRACE),
            ("spam", AppLogger.SPAM),
            ("verbose", AppLogger.VERBOSE),
            ("info", AppLogger.INFO),
            ("notice", AppLogger.NOTICE),
            ("success", AppLogger.SUCCESS),
            ("warning", AppLogger.WARNING),
            ("error", AppLogger.ERROR),
            ("critical", AppLogger.CRITICAL),
        ],
    )
    def test_every_level_round_trips_with_correct_stdlib_level(
        self, method, expected_level
    ):
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            log = StructLogger("structlog_test.levels")
            getattr(log, method)("event", x=1)
            assert len(handler.records) == 1
            assert handler.records[0].levelno == expected_level
        finally:
            logging.getLogger().removeHandler(handler)


class TestContextBinding:
    def test_bound_fields_appear_in_subsequent_calls(self):
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            log = StructLogger("structlog_test.bind").bind(request_id="abc123")
            log.info("first")
            log.info("second")
            assert "request_id='abc123'" in handler.records[0].getMessage()
            assert "request_id='abc123'" in handler.records[1].getMessage()
        finally:
            logging.getLogger().removeHandler(handler)

    def test_unbind_removes_context(self):
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            log = StructLogger("structlog_test.unbind").bind(request_id="abc123")
            log = log.unbind("request_id")
            log.info("event")
            assert "request_id" not in handler.records[0].getMessage()
        finally:
            logging.getLogger().removeHandler(handler)

    def test_new_clears_prior_context(self):
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            log = StructLogger("structlog_test.new").bind(a="1")
            log = log.new(b="2")
            log.info("event")
            message = handler.records[0].getMessage()
            assert "a=" not in message
            assert "b='2'" in message
        finally:
            logging.getLogger().removeHandler(handler)

    def test_bind_returns_new_instance(self):
        _configure()
        log = StructLogger("structlog_test.chain")
        bound = log.bind(x=1)
        assert bound is not log
        assert isinstance(bound, StructLogger)


class TestSameSink:
    def test_lands_in_same_handler_as_applogger_call(self):
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            struct_log = StructLogger("structlog_test.same_sink")
            plain_log = AppLogger.get_logger("structlog_test.same_sink")
            struct_log.info("from structlog")
            plain_log.info("from applogger")
            assert len(handler.records) == 2
            assert handler.records[0].name == handler.records[1].name
        finally:
            logging.getLogger().removeHandler(handler)

    def test_json_mode_output_contains_structured_fields(self, tmp_path):
        import json

        AppLogger._configured = False
        AppLogger.initialize(
            root_logger_name="structlog_test_json",
            level=TRACE,
            use_json=True,
            force_reconfigure=True,
        )
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        try:
            log = StructLogger("structlog_test_json.x").bind(request_id="r1")
            log.info("hello", extra=1)
            assert len(handler.records) == 1
            message = handler.records[0].getMessage()
            assert "request_id='r1'" in message
            assert "extra=1" in message
        finally:
            logging.getLogger().removeHandler(handler)


class TestOtelProcessor:
    _TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
    _SPAN_ID = 0x00F067AA0BA902B7

    def test_a_valid_span_adds_its_ids(self):
        trace = pytest.importorskip("opentelemetry.trace")
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=self._TRACE_ID,
                span_id=self._SPAN_ID,
                is_remote=False,
                trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
            )
        )
        with trace.use_span(span):
            result = otel_processor(None, "info", {"event": "hello"})
        assert result == {
            "event": "hello",
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            "span_id": "00f067aa0ba902b7",
        }

    def test_no_span_leaves_the_event_untouched(self):
        pytest.importorskip("opentelemetry.trace")
        assert otel_processor(None, "info", {"event": "hello"}) == {"event": "hello"}

    def test_unimportable_opentelemetry_leaves_the_event_untouched(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        assert otel_processor(None, "info", {"event": "hello"}) == {"event": "hello"}

    def test_the_configured_chain_renders_the_span_ids(self):
        trace = pytest.importorskip("opentelemetry.trace")
        _configure()
        handler = _ListHandler()
        logging.getLogger().addHandler(handler)
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=self._TRACE_ID,
                span_id=self._SPAN_ID,
                is_remote=False,
                trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
            )
        )
        try:
            with trace.use_span(span):
                StructLogger("structlog_test.otel").info("hello")
            message = handler.records[0].getMessage()
            assert "trace_id='4bf92f3577b34da6a3ce929d0e0e4736'" in message
        finally:
            logging.getLogger().removeHandler(handler)


class TestEscapeHatch:
    def test_structlog_property_is_bound_logger(self):
        import structlog as structlog_module

        _configure()
        log = StructLogger("structlog_test.escape")
        assert isinstance(log.structlog, structlog_module.stdlib.BoundLogger)


def test_import_rn_forge_commons_succeeds_without_structlog_named_module():
    # structlogger.py is not imported by rn_forge.commons's curated __init__.py.
    import rn_forge.commons

    assert not hasattr(rn_forge.commons, "StructLogger")
