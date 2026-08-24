"""Tests for rn_forge.commons.logging."""

from __future__ import annotations

import builtins
import logging
import inspect as stdlib_inspect
import types
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from rn_forge.commons import (
    AppLogger,
    LoggingConfig,
)
from rn_forge.commons.logging import (
    TRACE,
    BraceLogRecord,
    EnrichFilter,
    _enable_otel_log_correlation,
    _format_arguments,
    _resolve_variables,
    _try_enable_coloredlogs,
)
import rn_forge.commons.logging as logging_module

from conftest import raise_

GLOBAL_RESOLVE_VAR = "g"


# -- configuration helpers -------------------------------------------------


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


def test_initialize_registers_brace_log_record() -> None:
    _configure()
    assert logging.getLogRecordFactory() is BraceLogRecord


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

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        self.records.append(record)


def test_debug_and_trace_variables() -> None:
    _configure(level=logging.DEBUG)
    logger = _logger("test.vars")
    value = 42  # NOSONAR: read via frame introspection by debug_variables/trace_variables, not statically
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
    pytest.importorskip("pythonjsonlogger", reason="pythonjsonlogger not installed")
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
    monkeypatch.setattr(builtins, "__import__", _make_fake_import("opentelemetry"))
    _enable_otel_log_correlation(optional=True)  # should not raise


def test_enable_otel_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "__import__", _make_fake_import("opentelemetry"))
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
    seen: dict[str, bool] = {"color": False, "otel": False}

    monkeypatch.setattr(
        logging_module,
        "_try_enable_coloredlogs",
        lambda config: seen.__setitem__("color", True),
    )
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
    assert seen == {"color": True, "otel": True}


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


def test_try_enable_coloredlogs_missing_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "__import__", _make_fake_import("coloredlogs"))
    _try_enable_coloredlogs(LoggingConfig.build(root_logger_name="x"))


def test_try_enable_coloredlogs_install_failure_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_coloredlogs = types.SimpleNamespace(
        DEFAULT_FIELD_STYLES={},
        DEFAULT_LEVEL_STYLES={},
        install=lambda **kwargs: raise_(RuntimeError("install failed")),
    )
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "coloredlogs":
            return fake_coloredlogs
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    _try_enable_coloredlogs(LoggingConfig.build(root_logger_name="x"))


def test_format_arguments_fallback_on_bad_signature() -> None:
    result = _format_arguments(object(), (), {}, [], [])
    assert result == ["()", "{}"]


def test_format_arguments_include_and_exclude() -> None:
    def fn(a, b=2):
        return a + b

    assert _format_arguments(fn, (1,), {}, ["b"], []) == ["a=1"]
    assert _format_arguments(fn, (1,), {}, [], ["b"]) == ["b=2"]


def test_format_arguments_skips_self() -> None:
    class Sample:
        def method(self, value):
            return value

    parts = _format_arguments(Sample.method, (Sample(), 3), {}, [], [])
    assert parts == ["value=3"]


def test_resolve_variables_handles_none_frame() -> None:
    assert _resolve_variables("a,b", None) == ["<cannot resolve: a,b>"]


def test_resolve_variables_reads_globals_and_undefined() -> None:
    frame = stdlib_inspect.currentframe()
    resolved = _resolve_variables("GLOBAL_RESOLVE_VAR,missing_name", frame)
    assert "GLOBAL_RESOLVE_VAR='g'" in resolved
    assert "missing_name=<undefined>" in resolved


def test_audit_entry_error_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure()
    logger = _logger("test.audit.entryerr")
    module_logger = _logger(__name__)
    logger.setLevel(TRACE)
    module_logger.setLevel(TRACE)
    handler = _ListHandler()
    module_logger.addHandler(handler)
    monkeypatch.setattr(
        logging_module,
        "_format_arguments",
        lambda *args, **kwargs: raise_(RuntimeError("bad format")),
    )

    @logger.audit_method()
    def hello(name: str) -> str:
        return f"hi {name}"

    assert hello("alice") == "hi alice"
    assert any("audit_entry_error" in record.getMessage() for record in handler.records)
    module_logger.removeHandler(handler)


# Coverage ROI notes:
# - `logging.config.dictConfig`, `coloredlogs`, and OpenTelemetry integration are
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
