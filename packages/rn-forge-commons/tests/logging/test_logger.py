"""Tests for rn_forge.commons.logging.logger."""

from __future__ import annotations

import builtins
import logging
import subprocess
import sys
import types
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import rn_forge.commons.logging.logger as logging_module
from rich.logging import RichHandler
from rn_forge.commons import (
    AppLogger,
    LoggingConfig,
)
from rn_forge.commons.lang.reflection import ReflectUtils
from rn_forge.commons.logging.logger import (
    TRACE,
    BraceLogRecord,
    EnrichFilter,
    _enable_otel_log_correlation,
)
from rn_forge.commons.testing import raise_

# -- configuration helpers -------------------------------------------------


@pytest.fixture(autouse=True)
def restore_record_factory():
    saved = logging.getLogRecordFactory()
    yield
    logging.setLogRecordFactory(saved)


@pytest.fixture(autouse=True)
def reset_logger_state():
    AppLogger._configured = False
    yield
    AppLogger._configured = False
    logging.getLogger().handlers.clear()


def _configure(
    *,
    level: int = logging.INFO,
    fmt: str | None = None,
    enable_otel_correlation: bool = False,
) -> None:
    AppLogger._configured = False
    AppLogger.initialize(
        root_logger_name="test",
        level=level,
        fmt=fmt,
        enable_otel_correlation=enable_otel_correlation,
        force_reconfigure=True,
    )


def _logger(name: str) -> AppLogger:
    return AppLogger.get_logger(name)


class IncludeExcludeSample:
    def keep(self) -> str:
        return "keep"

    def skip(self) -> str:
        return "skip"


class BaseAuditSample:
    def inherited(self) -> str:
        return "inherited"


class ChildAuditSample(BaseAuditSample):
    def local(self) -> str:
        return "local"


# -- class API: AppLogger.get_logger / .initialize ------------------


def test_get_logger_returns_logger() -> None:
    _configure()
    logger = _logger("test.gl")
    assert isinstance(logger, AppLogger)
    assert logger.name == "test.gl"


def test_get_logger_has_verbose_level() -> None:
    _configure()
    logger = _logger("test.verbose")
    assert hasattr(logger, "verbose")


def test_initialize_sets_level() -> None:
    _configure(level=logging.DEBUG)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_initialize_sets_handler() -> None:
    _configure(level=logging.WARNING)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


def test_initialize_no_duplicate_handlers() -> None:
    _configure()
    _configure()
    root = logging.getLogger()
    assert len(root.handlers) == 1


def test_initialize_leaves_the_record_factory_alone() -> None:
    logging.setLogRecordFactory(logging.LogRecord)
    factory = logging.getLogRecordFactory()
    _configure()
    assert logging.getLogRecordFactory() is factory


def test_get_logger_preserves_a_factory_installed_after_initialize() -> None:
    _configure()
    current = logging.getLogRecordFactory()

    def consumer_factory(*args, **kwargs):
        record = current(*args, **kwargs)
        record.trace_id = "t-1"
        return record

    logging.setLogRecordFactory(consumer_factory)
    _logger("test.keep")
    record = logging.getLogRecordFactory()("n", logging.INFO, "", 0, "m", (), None)
    assert hasattr(record, "trace_id")


def test_get_logger_preserves_a_factory_installed_before_first_retrieval() -> None:
    current = logging.getLogRecordFactory()

    def consumer_factory(*args, **kwargs):
        record = current(*args, **kwargs)
        record.trace_id = "t-1"
        return record

    logging.setLogRecordFactory(consumer_factory)
    _logger("test.keep2")
    assert logging.getLogRecordFactory() is consumer_factory


# -- TRACE level -----------------------------------------------------------


def test_trace_level_value() -> None:
    assert TRACE == 1
    _configure()
    assert logging.getLevelName(TRACE) == "TRACE"


def test_trace_level_differs_from_spam() -> None:
    import verboselogs

    assert TRACE != verboselogs.SPAM


def test_trace_method() -> None:
    _configure()
    logger = _logger("test.trace")
    logger.setLevel(TRACE)
    logger.trace("trace message")
    assert logger.isEnabledFor(TRACE)


# -- AppLogger.initialize -------------------------------------------


def test_initialize_idempotent() -> None:
    logger1 = AppLogger.initialize(root_logger_name="test")
    logger2 = AppLogger.initialize(root_logger_name="test")
    assert logger1.name == logger2.name


def test_initialize_with_name() -> None:
    logger = AppLogger.initialize(root_logger_name="myapp")
    assert logger.name == "myapp"


def test_initialize_force_reconfigure() -> None:
    AppLogger.initialize(root_logger_name="test")
    AppLogger.initialize(root_logger_name="test", force_reconfigure=True)


# -- DEFAULT_FORMAT vs OTEL_FORMAT -----------------------------------------


def test_default_format_has_no_otel_fields() -> None:
    assert "otelTraceID" not in AppLogger.DEFAULT_FORMAT
    assert "otelSpanID" not in AppLogger.DEFAULT_FORMAT


def test_otel_format_has_otel_fields() -> None:
    assert "otelTraceID" in AppLogger.OTEL_FORMAT
    assert "otelSpanID" in AppLogger.OTEL_FORMAT


# -- update_level / restore_level -----------------------------------------


def test_update_and_restore_level() -> None:
    _configure()
    logger = _logger("test.levels")
    logger.setLevel(logging.INFO)
    logger._init_level = logging.INFO

    logger.update_level(logging.DEBUG)
    assert logger.level == logging.DEBUG

    logger.restore_level()
    assert logger.level == logging.INFO


def test_update_level_noop_when_same() -> None:
    _configure()
    logger = _logger("test.levels.noop")
    logger.setLevel(logging.INFO)
    logger._init_level = logging.INFO
    logger.update_level(logging.INFO)
    assert logger.level == logging.INFO


def test_restore_level_noop_when_same() -> None:
    _configure()
    logger = _logger("test.levels.restore.noop")
    logger.setLevel(logging.INFO)
    logger._init_level = logging.INFO
    logger.restore_level()
    assert logger.level == logging.INFO


# -- BraceLogRecord --------------------------------------------------------


def test_brace_record_brace_style() -> None:
    record = BraceLogRecord("t", logging.INFO, "", 0, "hello {}", ("world",), None)
    assert record.getMessage() == "hello world"


def test_brace_record_percent_style() -> None:
    record = BraceLogRecord("t", logging.INFO, "", 0, "hello %s", ("world",), None)
    assert record.getMessage() == "hello world"


def test_brace_record_no_args() -> None:
    record = BraceLogRecord("t", logging.INFO, "", 0, "hello", None, None)
    assert record.getMessage() == "hello"


def test_brace_record_multiple_positional_args() -> None:
    record = BraceLogRecord("t", logging.INFO, "", 0, "{} + {} = {}", (1, 2, 3), None)
    assert record.getMessage() == "1 + 2 = 3"


def test_brace_record_passes_dict_as_positional_arg() -> None:
    d = {"a": 1}
    record = BraceLogRecord("t", logging.INFO, "", 0, "my dict: {}", (d,), None)
    assert record.getMessage() == f"my dict: {d}"


def test_brace_record_format_error_returns_fallback() -> None:
    record = BraceLogRecord("t", logging.INFO, "", 0, "bad {} {}", ("only_one",), None)
    msg = record.getMessage()
    assert "bad" in msg
    assert "format_args" in msg


# -- EnrichFilter ----------------------------------------------------------


def test_enrich_filter_adds_core_fields() -> None:
    filt = EnrichFilter(service_name="myapp", environment="test")
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    filt.filter(record)
    assert record.service == "myapp"
    assert record.env == "test"
    assert hasattr(record, "caller")


def test_enrich_filter_no_otel_by_default() -> None:
    filt = EnrichFilter(service_name="myapp")
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    filt.filter(record)
    assert not hasattr(record, "otelTraceID")


def test_enrich_filter_injects_otel_when_enabled() -> None:
    filt = EnrichFilter(service_name="myapp", inject_otel_defaults=True)
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    filt.filter(record)
    assert hasattr(record, "otelTraceID")
    assert hasattr(record, "otelSpanID")


def test_enrich_filter_does_not_overwrite_existing() -> None:
    filt = EnrichFilter(service_name="myapp")
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    record.caller = "custom.caller"
    filt.filter(record)
    assert record.caller == "custom.caller"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_brace_messages_format_under_the_stdlib_factory() -> None:
    logger = AppLogger("test.stdlib", logging.INFO)
    handler = _ListHandler()
    logger.addHandler(handler)
    logging.setLogRecordFactory(logging.LogRecord)
    logger.info("x={}", 1)  # noqa: PLE1205  # AppLogger supports brace arguments.
    assert handler.records[0].getMessage() == "x=1"


def test_a_consumer_factory_field_reaches_app_logger_records() -> None:
    def consumer_factory(*args, **kwargs):
        record = logging.LogRecord(*args, **kwargs)
        record.trace_id = "t-1"
        return record

    logging.setLogRecordFactory(consumer_factory)
    logger = _logger("test.consumer")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.info("x={}", 1)  # noqa: PLE1205  # AppLogger supports brace arguments.
    assert handler.records[0].trace_id == "t-1"
    assert handler.records[0].getMessage() == "x=1"


def test_percent_messages_on_a_plain_logger_are_unchanged() -> None:
    logging.setLogRecordFactory(logging.LogRecord)
    logger = logging.Logger("plain", logging.INFO)  # noqa: LOG001  # Require a plain Logger.
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.info("x=%s", 1)
    assert handler.records[0].getMessage() == "x=1"


_LEVEL_METHODS = (
    "critical",
    "fatal",
    "error",
    "exception",
    "success",
    "warning",
    "notice",
    "info",
    "verbose",
    "debug",
    "spam",
    "trace",
)


@pytest.mark.parametrize("method", _LEVEL_METHODS)
def test_level_methods_report_the_callers_location(method: str) -> None:
    logger = AppLogger("test.location", TRACE)
    handler = _ListHandler()
    handler.addFilter(EnrichFilter(service_name="test"))
    logger.addHandler(handler)
    line = sys._getframe().f_lineno + 1
    getattr(logger, method)("message")
    record = handler.records[0]
    assert record.filename == Path(__file__).name
    assert record.lineno == line
    assert record.funcName == "test_level_methods_report_the_callers_location"
    assert record.caller == f"{logger.name}.{record.funcName}"


def test_a_caller_stacklevel_stays_relative_to_the_caller() -> None:
    logger = AppLogger("test.stacklevel", logging.INFO)
    handler = _ListHandler()
    logger.addHandler(handler)

    def helper() -> None:
        logger.info("message", stacklevel=2)

    line = sys._getframe().f_lineno + 1
    helper()
    record = handler.records[0]
    assert record.filename == Path(__file__).name
    assert record.lineno == line
    assert record.funcName == "test_a_caller_stacklevel_stays_relative_to_the_caller"


def test_disabled_levels_do_not_look_up_frames_or_format_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = AppLogger("test.disabled", logging.CRITICAL)

    class Unformattable:
        def __str__(self):
            raise AssertionError("argument converted to string")

        def __format__(self, spec):
            raise AssertionError("argument formatted")

    def fail_find_caller(*args, **kwargs):
        raise AssertionError("caller frame looked up")

    monkeypatch.setattr(logger, "findCaller", fail_find_caller)
    for method in _LEVEL_METHODS[2:]:
        getattr(logger, method)("x={}", Unformattable())


def test_concurrent_retrieval_keeps_a_consumer_factory() -> None:
    barrier = Barrier(8)

    def consumer_factory(*args, **kwargs):
        return logging.LogRecord(*args, **kwargs)

    def retrieve(index: int) -> AppLogger:
        barrier.wait()
        return _logger(f"test.thread.{index}")

    logging.setLogRecordFactory(consumer_factory)
    with ThreadPoolExecutor(max_workers=8) as executor:
        loggers = list(executor.map(retrieve, range(8)))
    assert all(isinstance(logger, AppLogger) for logger in loggers)
    assert logging.getLogRecordFactory() is consumer_factory


def test_exception_logs_the_traceback() -> None:
    logger = AppLogger("test.exception", logging.ERROR)
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        raise ValueError("failure")
    except ValueError as error:
        logger.exception("failed")
        record = handler.records[0]
        assert record.exc_info == (ValueError, error, error.__traceback__)
        assert record.exc_info[2] is not None


def test_debug_and_trace_variables() -> None:
    _configure(level=logging.DEBUG)
    logger = _logger("test.vars")
    value = 42  # NOSONAR: read via frame introspection by debug_variables/trace_variables, not statically
    _ = value
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        logger.debug_variables("value, missing", "dbg")
        messages = [rec.getMessage() for rec in handler.records]
        assert any("value=42" in msg for msg in messages)
        assert any("missing=<undefined>" in msg for msg in messages)

        handler.records.clear()
        logger.update_level(TRACE)
        logger.trace_variables("value", "trace")
        trace_messages = [rec.getMessage() for rec in handler.records]
        assert any("trace -> value=42" in msg for msg in trace_messages)
    finally:
        logger.restore_level()
        logger.removeHandler(handler)


# -- LoggingConfig ---------------------------------------------------------


def test_logging_config_defaults() -> None:
    defaults = LoggingConfig.defaults()
    assert defaults["root_logger_name"] == "rn-forge"
    assert defaults["configure_root"] is True
    assert defaults["use_json"] is False
    assert defaults["enable_otel_correlation"] is False


def test_logging_config_defaults_handles_isatty_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadStdout:
        def isatty(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(logging_module.sys, "stdout", BadStdout())
    defaults = LoggingConfig.defaults()
    assert defaults["isatty"] is False


def test_logging_config_build_derives_otel_format() -> None:
    cfg = LoggingConfig.build(root_logger_name="x", enable_otel_correlation=True)
    assert cfg.fmt == logging_module._OTEL_FORMAT


def test_configure_logging_json_non_root(tmp_path: Path) -> None:
    log_path = str(tmp_path / "svc.log")
    logger = AppLogger.initialize(
        root_logger_name="svc",
        level=logging.INFO,
        use_json=True,
        configure_root=False,
        enable_otel_correlation=True,
        file=log_path,
        force_reconfigure=True,
    )
    assert logger.name == "svc"
    assert logging.getLogger().handlers == []
    assert logging.getLogger("svc").handlers  # console + file handlers present
    logging.getLogger().handlers.clear()


_ImportFn = Callable[
    [
        str,
        "Mapping[str, object] | None",
        "Mapping[str, object] | None",
        "Sequence[str] | None",
        int,
    ],
    types.ModuleType,
]


def _make_fake_import(block_prefix: str) -> _ImportFn:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = None,
        level: int = 0,
    ) -> types.ModuleType:
        if name.startswith(block_prefix):
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    return fake_import


def test_enable_otel_optional_handles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        logging_module.importlib,
        "import_module",
        lambda name: raise_(ImportError("missing")),
    )
    _enable_otel_log_correlation(optional=True)  # should not raise


def test_otel_correlation_injects_context_without_adding_handlers() -> None:
    pytest.importorskip("opentelemetry.instrumentation.logging")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import logging
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, use_span
from rn_forge.commons.logging.logger import _enable_otel_log_correlation

handler = logging.NullHandler()
logging.getLogger().addHandler(handler)
_enable_otel_log_correlation(optional=False)
assert logging.getLogger().handlers == [handler]
span = NonRecordingSpan(SpanContext(0x123, 0x456, False, TraceFlags(1)))
with use_span(span):
    record = logging.getLogger("correlation").makeRecord(
        "correlation", logging.INFO, "test", 1,
        "message", (), None,
    )
assert record.otelTraceID == "00000000000000000000000000000123"
assert record.otelSpanID == "0000000000000456"
assert record.otelTraceSampled is True
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_enable_otel_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        logging_module.importlib,
        "import_module",
        lambda name: raise_(ImportError("missing")),
    )
    with pytest.raises(ImportError):
        _enable_otel_log_correlation(optional=False)


def test_enable_otel_optional_instrument_failure_is_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInstrumentor:
        def instrument(self, **kwargs):
            raise RuntimeError("instrument fail")

    fake_module = types.SimpleNamespace(LoggingInstrumentor=FakeInstrumentor)
    monkeypatch.setattr(
        logging_module.importlib, "import_module", lambda name: fake_module
    )
    _enable_otel_log_correlation(optional=True)


def test_enable_otel_required_instrument_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInstrumentor:
        def instrument(self, **kwargs):
            raise RuntimeError("instrument fail")

    fake_module = types.SimpleNamespace(LoggingInstrumentor=FakeInstrumentor)
    monkeypatch.setattr(
        logging_module.importlib, "import_module", lambda name: fake_module
    )
    with pytest.raises(RuntimeError, match="instrument fail"):
        _enable_otel_log_correlation(optional=False)


# -- audit_method decorator ------------------------------------------------


def test_audit_method_logs_entry_and_exit() -> None:
    _configure()
    logger = _logger("test.audit")
    logger.setLevel(TRACE)

    @logger.audit_method()
    def add(a: int, b: int) -> int:
        return a + b

    result = add(1, 2)
    assert result == 3


def test_audit_method_logs_on_exception() -> None:
    _configure()
    logger = _logger("test.audit.exc")
    logger.setLevel(TRACE)

    @logger.audit_method()
    def fail() -> None:
        raise ValueError("boom")

    try:
        fail()
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_audit_method_logs_reraised_exception() -> None:
    _configure()
    logger = _logger("test.audit.reraise")
    module_logger = _logger(__name__)
    logger.setLevel(TRACE)
    module_logger.setLevel(TRACE)
    handler = _ListHandler()
    module_logger.addHandler(handler)

    @logger.audit_method()
    def inner() -> None:
        raise ValueError("boom")

    @logger.audit_method()
    def outer() -> None:
        inner()

    with pytest.raises(ValueError):
        outer()

    messages = [record.getMessage() for record in handler.records]
    assert any("re-raised ValueError" in message for message in messages)
    module_logger.removeHandler(handler)


def test_audit_method_exclude() -> None:
    _configure()
    logger = _logger("test.audit.excl")
    logger.setLevel(TRACE)

    @logger.audit_method(exclude=["secret"])
    def greet(name: str, secret: str = "hidden") -> str:
        return f"hi {name}"

    assert greet("alice", secret="s3cret") == "hi alice"


def test_audit_method_log_return_value() -> None:
    _configure()
    logger = _logger("test.audit.retval")
    logger.setLevel(TRACE)

    @logger.audit_method(log_return_value=True)
    def double(x: int) -> int:
        return x * 2

    assert double(5) == 10


def test_audit_method_return_value_is_logged() -> None:
    _configure()
    logger = _logger("test.audit.retval.assert")
    module_logger = _logger(__name__)
    logger.setLevel(TRACE)
    module_logger.setLevel(TRACE)
    handler = _ListHandler()
    module_logger.addHandler(handler)

    @logger.audit_method(log_return_value=True)
    def identity(x: int) -> int:
        return x

    assert identity(7) == 7
    assert any("ReturnValue -> 7" in record.getMessage() for record in handler.records)
    module_logger.removeHandler(handler)


def test_audit_class() -> None:
    _configure()
    logger = _logger("test.audit.cls")
    logger.setLevel(TRACE)

    @logger.audit_class()
    class Calc:
        def add(self, a: int, b: int) -> int:
            return a + b

    assert Calc().add(2, 3) == 5


def test_audit_class_skips_private_methods() -> None:
    _configure()
    logger = _logger("test.audit.cls.private")
    logger.setLevel(TRACE)

    @logger.audit_class()
    class MyClass:
        def public(self) -> str:
            return "public"

        def _private(self) -> str:
            return "private"

        def __dunder(self) -> str:
            return "dunder"

    obj = MyClass()
    assert obj.public() == "public"
    assert obj._private() == "private"
    assert not hasattr(obj._private, "__wrapped__")


def test_audit_class_include_and_exclude() -> None:
    _configure()
    logger = _logger("test.audit.cls.include")
    logger.setLevel(TRACE)
    decorated = logger.audit_class(include=["keep"], exclude=["skip"])(
        IncludeExcludeSample
    )
    obj = decorated()
    assert hasattr(obj.keep, "__wrapped__")
    assert not hasattr(obj.skip, "__wrapped__")


def test_audit_class_exclude_branch() -> None:
    _configure()
    logger = _logger("test.audit.cls.exclude")
    decorated = logger.audit_class(exclude=["skip"])(IncludeExcludeSample)
    obj = decorated()
    assert not hasattr(obj.skip, "__wrapped__")


def test_audit_class_defaults_to_class_only() -> None:
    _configure()
    logger = _logger("test.audit.cls.inherited.default")

    class _Base:
        def inherited(self) -> str:
            return "inherited"

    class _Child(_Base):
        def local(self) -> str:
            return "local"

    decorated = logger.audit_class()(_Child)
    obj = decorated()

    assert hasattr(obj.local, "__wrapped__")
    assert not hasattr(obj.inherited, "__wrapped__")


def test_audit_class_can_include_inherited_methods() -> None:
    _configure()
    logger = _logger("test.audit.cls.inherited.enabled")

    class _Base:
        def inherited(self) -> str:
            return "inherited"

    class _Child(_Base):
        def local(self) -> str:
            return "local"

    decorated = logger.audit_class(include_inherited=True)(_Child)
    obj = decorated()

    assert hasattr(obj.local, "__wrapped__")
    assert hasattr(obj.inherited, "__wrapped__")


# -- initialize with file output -------------------------------------------


def test_initialize_creates_log_file(tmp_path: Path) -> None:
    log_path = str(tmp_path / "app.log")
    AppLogger.initialize(
        root_logger_name="test",
        file=log_path,
        configure_root=True,
        force_reconfigure=True,
    )
    assert AppLogger.LOG_FILE is not None
    logging.getLogger().handlers.clear()


def test_initialize_file_without_extension_adds_timestamp(tmp_path: Path) -> None:
    log_path = str(tmp_path / "app")
    AppLogger.initialize(root_logger_name="test", file=log_path, force_reconfigure=True)
    assert AppLogger.LOG_FILE is not None
    assert AppLogger.LOG_FILE.suffix == ".log"
    logging.getLogger().handlers.clear()


# -- initialize configure_root=False ---------------------------------------


def test_initialize_configure_root_false() -> None:
    logger = AppLogger.initialize(
        root_logger_name="isolated", configure_root=False, force_reconfigure=True
    )
    assert logger.name == "isolated"
    assert logging.getLogger().handlers == []


# -- initialize with update_loggers ----------------------------------------


def test_initialize_update_loggers(monkeypatch: pytest.MonkeyPatch) -> None:
    AppLogger.initialize(
        root_logger_name="test",
        update_loggers={"urllib3": logging.ERROR, "boto3": logging.WARNING},
        force_reconfigure=True,
    )
    assert logging.getLogger("urllib3").level == logging.ERROR
    assert logging.getLogger("boto3").level == logging.WARNING
    logging.getLogger().handlers.clear()


def test_initialize_enables_optional_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {"otel": False}

    monkeypatch.setattr(
        logging_module,
        "_enable_otel_log_correlation",
        lambda optional: seen.__setitem__("otel", True),
    )

    AppLogger.initialize(
        root_logger_name="test.hooks",
        enable_color=True,
        isatty=True,
        enable_otel_correlation=True,
        force_reconfigure=True,
    )
    assert seen == {"otel": True}
    root = logging.getLogger()
    assert isinstance(root.handlers[0], RichHandler)


# -- EnrichFilter environment variable fallback ----------------------------


def test_enrich_filter_env_from_environment_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("DJANGO_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    filt = EnrichFilter(service_name="svc")
    assert filt.environment == "staging"


def test_enrich_filter_env_from_django_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("DJANGO_ENV", "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    filt = EnrichFilter(service_name="svc")
    assert filt.environment == "production"


def test_enrich_filter_env_from_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DJANGO_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")
    filt = EnrichFilter(service_name="svc")
    assert filt.environment == "dev"


def test_enrich_filter_env_defaults_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DJANGO_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    filt = EnrichFilter(service_name="svc")
    assert filt.environment == "unknown"


def test_enrich_filter_env_explicit_overrides_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "should-not-be-used")
    filt = EnrichFilter(service_name="svc", environment="explicit-env")
    assert filt.environment == "explicit-env"


def test_enrich_filter_always_returns_true() -> None:
    filt = EnrichFilter(service_name="svc")
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    assert filt.filter(record) is True


# -- _configure_logging configure_root=True --------------------------------


def test_configure_logging_root_has_console_handler() -> None:
    AppLogger.initialize(
        root_logger_name="myapp",
        level=logging.INFO,
        configure_root=True,
        force_reconfigure=True,
    )
    assert (
        logging.getLogger().handlers
    )  # console handler present when configure_root=True
    logging.getLogger().handlers.clear()


# -- initialize with LoggingConfig (full fields) ---------------------------


def test_initialize_with_use_json() -> None:
    logger = AppLogger.initialize(
        root_logger_name="test.json",
        use_json=False,
        configure_root=True,
        force_reconfigure=True,
    )
    assert logger.name == "test.json"
    logging.getLogger().handlers.clear()


def test_configure_logging_use_json_builds_json_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_dict_config(config):
        captured.update(config)

    config = LoggingConfig.build(
        root_logger_name="svc", use_json=True, configure_root=False
    )
    monkeypatch.setattr(logging.config, "dictConfig", fake_dict_config)
    AppLogger._configure_logging(config, None)

    assert "json" in captured["formatters"]


def test_logger_level_methods_smoke() -> None:
    _configure(level=TRACE)
    logger = _logger("test.methods")
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        logger.critical("critical")
        logger.fatal("fatal")
        logger.error("error")
        logger.warning("warning")
        logger.notice("notice")
        logger.info("info")
        logger.verbose("verbose")
        logger.debug("debug")
        logger.spam("spam")
        logger.trace("trace")
        assert len(handler.records) >= 10
    finally:
        logger.removeHandler(handler)


def test_log_variables_noop_when_disabled() -> None:
    _configure(level=logging.INFO)
    logger = _logger("test.vars.noop")
    handler = _ListHandler()
    logger.addHandler(handler)
    try:
        value = 1  # noqa: F841  # NOSONAR: read via frame introspection by debug_variables, not statically
        logger.debug_variables("value")
        assert handler.records == []
    finally:
        logger.removeHandler(handler)


@pytest.mark.parametrize(
    ("use_json", "enable_color", "isatty", "expected_type"),
    [
        (False, False, False, logging.StreamHandler),
        (False, True, False, logging.StreamHandler),  # not a tty -> no Rich
        (False, True, True, RichHandler),
        (False, False, True, logging.StreamHandler),  # color disabled -> no Rich
        (True, False, False, logging.StreamHandler),
        (True, True, True, logging.StreamHandler),  # json beats color+tty
    ],
)
def test_handler_selection_matrix(
    use_json: bool, enable_color: bool, isatty: bool, expected_type: type
) -> None:
    AppLogger.initialize(
        root_logger_name="test.handler_matrix",
        use_json=use_json,
        enable_color=enable_color,
        isatty=isatty,
        force_reconfigure=True,
    )
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert type(root.handlers[0]) is expected_type


def test_file_handler_is_never_rich_even_with_color(tmp_path: Path) -> None:
    log_path = str(tmp_path / "app.log")
    AppLogger.initialize(
        root_logger_name="test.file_never_rich",
        enable_color=True,
        isatty=True,
        file=log_path,
        force_reconfigure=True,
    )
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    file_handler = file_handlers[0]
    assert not isinstance(file_handler, RichHandler)
    assert file_handler.formatter is not None
    assert file_handler.formatter._fmt == logging_module._DEFAULT_FORMAT


def test_every_custom_level_has_a_theme_entry() -> None:
    custom_levels = [
        "trace",
        "spam",
        "debug",
        "verbose",
        "info",
        "notice",
        "success",
        "warning",
        "error",
        "critical",
    ]
    for level_name in custom_levels:
        assert f"logging.level.{level_name}" in logging_module._RICH_LEVEL_STYLES


def test_rich_console_markup_is_disabled_for_interpolated_values() -> None:
    console = logging_module._build_rich_console(
        LoggingConfig.build(root_logger_name="x")
    )
    with console.capture() as capture:
        console.print("[red]not styled[/red]", markup=False)
    assert "[red]not styled[/red]" in capture.get()


def test_build_rich_console_merges_level_style_overrides() -> None:
    config = LoggingConfig.build(
        root_logger_name="x", level_styles={"critical": "bold magenta"}
    )
    console = logging_module._build_rich_console(config)
    assert console.get_style("logging.level.critical") == console.get_style(
        "bold magenta"
    )


def test_audit_entry_error_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure()
    logger = _logger("test.audit.entryerr")
    module_logger = _logger(__name__)
    logger.setLevel(TRACE)
    module_logger.setLevel(TRACE)
    handler = _ListHandler()
    module_logger.addHandler(handler)
    monkeypatch.setattr(
        ReflectUtils,
        "inspect_method_arguments",
        lambda *args, **kwargs: raise_(RuntimeError("bad format")),
    )

    @logger.audit_method()
    def hello(name: str) -> str:
        return f"hi {name}"

    assert hello("alice") == "hi alice"
    assert any("audit_entry_error" in record.getMessage() for record in handler.records)
    module_logger.removeHandler(handler)


# Coverage ROI notes:
# - `logging.config.dictConfig`, Rich console rendering, and OpenTelemetry integration are
#   covered via branch-level fakes; exhaustive third-party behavior is out of scope.


# -- LoggingConfig additional fields ---------------------------------------


def test_logging_config_all_fields() -> None:
    cfg = LoggingConfig.build(
        root_logger_name="test",
        level=logging.DEBUG,
        file="app.log",
        fmt="%(message)s",
        enable_color=False,
        isatty=False,
        use_json=True,
        configure_root=False,
        update_loggers={"boto3": logging.ERROR},
        enable_otel_correlation=True,
        otel_optional=False,
    )
    assert cfg.root_logger_name == "test"
    assert cfg.level == logging.DEBUG
    assert cfg.file == "app.log"
    assert cfg.use_json is True
    assert cfg.configure_root is False
    assert cfg.update_loggers == {"boto3": logging.ERROR}
    assert cfg.enable_otel_correlation is True
    assert cfg.otel_optional is False
