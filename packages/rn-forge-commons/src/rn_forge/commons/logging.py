"""Structured logging utilities for Python applications.

- Explicit, idempotent initialisation via :meth:`AppLogger.initialize`.
- Uses the more recommended approach of configuring logging via ``dictConfig``.
- Inherits from :class:`~verboselogs.VerboseLogger` and adds custom levels (``TRACE``),
  ``{}``-style formatting, and method-audit decorators.
- Safe record enrichment via :class:`EnrichFilter` (caller / service / env +
  optional OpenTelemetry correlation placeholders).
"""

from __future__ import annotations

import functools
import importlib
import inspect
import logging
from operator import attrgetter as _attrgetter
import logging.config
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, cast

import verboselogs
from rn_forge.commons._typing import VerboseLoggerBase
from rn_forge.commons.reflection import ReflectUtils

# ---------------------------------------------------------------------------
# TRACE level — below SPAM (5) and DEBUG (10).
# verboselogs uses SPAM=5, so TRACE=1 avoids collision.
# ---------------------------------------------------------------------------
TRACE = 1

# Log format strings
_DEFAULT_FORMAT = (
    "%(asctime)s,%(msecs)03d %(threadName)s[%(process)d] "
    "%(caller)s %(levelname)s "
    "[svc=%(service)s env=%(env)s] "
    "%(message)s"
)
_OTEL_FORMAT = (
    "%(asctime)s,%(msecs)03d %(threadName)s[%(process)d] "
    "%(caller)s %(levelname)s "
    "[svc=%(service)s env=%(env)s "
    "trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] "
    "%(message)s"
)

# Parameters that are always excluded from audit logging.
_AUDIT_SELF_PARAMS = frozenset({"self", "cls"})


# ---------------------------------------------------------------------------
# BraceLogRecord — process-wide {}-style support via setLogRecordFactory
# ---------------------------------------------------------------------------
class BraceLogRecord(logging.LogRecord):
    """LogRecord subclass whose ``getMessage`` handles both ``%``- and ``{}``-style messages.

    Registered globally via ``logging.setLogRecordFactory`` so every handler
    in the process — including coloredlogs, JSON formatters, and file handlers —
    receives correctly formatted messages without any per-handler coupling.

    ``%``-style is tried first so third-party libraries that rely on it are
    completely unaffected.
    """

    def getMessage(self) -> str:
        msg = str(self.msg)
        if not self.args:
            return msg

        # Dispatch on % presence — delegates to stdlib to preserve its exact contract.
        if "%" in msg:
            return super().getMessage()

        # {}-style formatting for AppLogger callers.
        # Note: logging normalises a single (dict,) arg to the dict itself, so
        # we must not star-unpack a dict (that would iterate its keys).
        try:
            if isinstance(self.args, tuple):
                return msg.format(*self.args)
            return msg.format(self.args)
        except Exception:
            return f"{msg} | format_args={self.args!r}"


# ---------------------------------------------------------------------------
# EnrichFilter — adds caller / service / env / OTel fields via Filter
# ---------------------------------------------------------------------------
class EnrichFilter(logging.Filter):
    """Injects consistent fields into every log record.

    Fields always added:

    - ``caller``: ``<logger name>.<funcName>``
    - ``service``, ``env``: identity fields from constructor / env-vars

    OTel placeholder fields (``otelTraceID``, ``otelSpanID``,
    ``otelServiceName``, ``otelTraceSampled``) are only injected when
    *inject_otel_defaults* is ``True``, preventing noisy ``trace_id=-``
    output when OpenTelemetry is not in use.
    """

    def __init__(
        self,
        service_name: str,
        environment: str | None = None,
        *,
        inject_otel_defaults: bool = False,
    ) -> None:
        """Initialize :class:`EnrichFilter`.

        Args:
            service_name: Identifier for the running service, injected as the
                ``service`` field on every log record.
            environment: Deployment environment string (e.g. ``"production"``).
                When ``None``, resolved from the environment variables
                ``ENVIRONMENT``, ``DJANGO_ENV``, or ``APP_ENV`` in that order,
                falling back to ``"unknown"``.
            inject_otel_defaults: When ``True``, inject ``otelTraceID``,
                ``otelSpanID``, ``otelServiceName``, and ``otelTraceSampled``
                placeholder fields on records that do not already have them.
                Defaults to ``False``.
        """
        super().__init__()
        self.service_name = service_name
        self.environment = (
            environment
            or os.getenv("ENVIRONMENT")
            or os.getenv("DJANGO_ENV")
            or os.getenv("APP_ENV")
            or "unknown"
        )
        self.inject_otel_defaults = inject_otel_defaults

    def filter(self, record: logging.LogRecord) -> bool:
        """Enrich *record* with ``service``, ``env``, ``caller``, and optional OTel fields.

        Always returns ``True`` (the record is never suppressed).

        Args:
            record: The log record to enrich in-place.

        Returns:
            Always ``True``.
        """
        if not hasattr(record, "service"):
            record.service = self.service_name
        if not hasattr(record, "env"):
            record.env = self.environment
        if not hasattr(record, "caller"):
            record.caller = f"{record.name}.{record.funcName}"

        if self.inject_otel_defaults:
            for attr, default in (
                ("otelTraceID", "-"),
                ("otelSpanID", "-"),
                ("otelServiceName", self.service_name),
                ("otelTraceSampled", "false"),
            ):
                if not hasattr(record, attr):
                    setattr(record, attr, default)

        return True


# ---------------------------------------------------------------------------
# LoggingConfig — opinionated defaults that work in Django and non-Django
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LoggingConfig:
    """Resolved logging configuration produced by :meth:`build`.

    Do not construct directly — use :meth:`build` so that all defaults are
    applied.  All fields are guaranteed to have a value after ``build()``;
    ``file`` is the only field that can be ``None`` (meaning no file handler).
    """

    root_logger_name: str
    level: int
    file: str | None
    fmt: str
    enable_color: bool
    isatty: bool
    use_json: bool
    configure_root: bool
    update_loggers: dict[str, int]
    enable_otel_correlation: bool
    otel_optional: bool
    field_styles: dict[str, Any]
    level_styles: dict[str, Any]

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Return all concrete defaults as a plain dict.

        This is the single source of truth for every default value.
        Dynamic defaults (TTY detection, env-var level) are resolved here
        at call time, not at import time.
        """
        try:
            isatty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        except Exception:
            isatty = False

        return {
            "root_logger_name": "rn-forge",
            "level": getattr(
                verboselogs,
                os.environ.get("DEFAULT_LOG_LEVEL", "VERBOSE").upper(),
                verboselogs.VERBOSE,
            ),  # env: DEFAULT_LOG_LEVEL
            "file": None,  # no file handler by default
            "fmt": os.environ.get(
                "DEFAULT_LOG_FORMAT", _DEFAULT_FORMAT
            ),  # env: DEFAULT_LOG_FORMAT; swapped to _OTEL_FORMAT by build() when enable_otel_correlation=True
            "isatty": isatty,  # auto-detected from sys.stdout at configuration time
            "enable_color": isatty,  # colour on when stdout is a TTY
            "use_json": False,  # plain-text output by default
            "configure_root": True,  # configure the root logger; set False inside libraries
            "update_loggers": {},  # no third-party logger overrides by default
            "enable_otel_correlation": False,  # OTel trace/span injection disabled by default
            "otel_optional": True,  # suppress ImportError when opentelemetry is absent
            "field_styles": {
                "caller": {"bold": True, "bright": True}
            },  # style the injected caller field
            "level_styles": {
                "critical": {"background": "red", "bold": True}
            },  # make critical visually distinct
        }

    @classmethod
    def build(cls, **overrides: Any) -> LoggingConfig:
        """Return a fully-resolved config by merging *overrides* onto :meth:`defaults`.

        ``None`` values in *overrides* are treated as "not provided" and
        fall back to the default.  Pass ``False`` or ``0`` to explicitly
        override a truthy default.

        ``fmt`` is derived from ``enable_otel_correlation`` when not explicitly
        provided: ``_OTEL_FORMAT`` is used when OTel correlation is enabled,
        ``_DEFAULT_FORMAT`` otherwise.
        """
        merged = {
            **cls.defaults(),
            **{k: v for k, v in overrides.items() if v is not None},
        }
        # Derive fmt from enable_otel_correlation when not explicitly overridden
        if overrides.get("fmt") is None and merged.get("enable_otel_correlation"):
            merged["fmt"] = os.environ.get("DEFAULT_LOG_FORMAT", _OTEL_FORMAT)
        return cls(**merged)


# ---------------------------------------------------------------------------
# AppLogger
# ---------------------------------------------------------------------------
class AppLogger(VerboseLoggerBase):
    """Custom logger with TRACE level, runtime level switching, and audit decorators.

    Extends :class:`verboselogs.VerboseLogger` which already provides
    ``verbose``, ``notice``, ``spam``, and ``success`` levels.

    Call :meth:`initialize` once at process start-up (e.g. in
    ``main()``, ``wsgi.py``, or ``AppConfig.ready()``).

    Typical usage::

        logger = AppLogger.initialize(root_logger_name="billing", level=AppLogger.INFO)
        logger.info("service started | version={}", "1.2.3")

        app_logger = AppLogger.get_logger(__name__)
        app_logger.debug("request_id={}", request_id)
    """

    NOTSET = logging.NOTSET
    CRITICAL = logging.CRITICAL
    FATAL = logging.FATAL
    ERROR = logging.ERROR
    SUCCESS = verboselogs.SUCCESS
    WARNING = logging.WARNING
    NOTICE = verboselogs.NOTICE
    INFO = logging.INFO
    VERBOSE = verboselogs.VERBOSE
    DEBUG = logging.DEBUG
    SPAM = verboselogs.SPAM
    TRACE = TRACE

    DEFAULT_FORMAT: str = _DEFAULT_FORMAT
    OTEL_FORMAT: str = _OTEL_FORMAT

    LOG_FILE: Path | None = None

    __slots__ = ("_init_level", "_audit_level", "_audit_separator")

    _config_lock = threading.Lock()
    _configured: bool = False

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        """Initialize :class:`AppLogger`.

        Reads the ``AUDIT_LOG_LEVEL`` (default ``"SPAM"``) and
        ``AUDIT_FIELD_SEPARATOR`` (default ``" | "``) environment variables
        to configure audit decorator behaviour.

        Args:
            name: Logger name passed to the underlying
                :class:`verboselogs.VerboseLogger`.
            level: Initial log level. Defaults to :data:`logging.NOTSET`.
        """
        super().__init__(name, level)  # verboselogs lacks stubs
        self._init_level = self.level
        self._audit_level = getattr(
            self, os.environ.get("AUDIT_LOG_LEVEL", "SPAM").upper(), verboselogs.SPAM
        )
        self._audit_separator = os.environ.get("AUDIT_FIELD_SEPARATOR", " | ")

    # -- configuration -----------------------------------------------------

    # All keyword-only, one per LoggingConfig.build() override.
    @staticmethod
    def initialize(  # NOSONAR
        *,
        root_logger_name: str,
        level: int | None = None,
        file: str | None = None,
        fmt: str | None = None,
        enable_color: bool | None = None,
        isatty: bool | None = None,
        use_json: bool | None = None,
        configure_root: bool | None = None,
        update_loggers: dict[str, int] | None = None,
        enable_otel_correlation: bool | None = None,
        otel_optional: bool | None = None,
        field_styles: dict[str, Any] | None = None,
        level_styles: dict[str, Any] | None = None,
        force_reconfigure: bool = False,
    ) -> AppLogger:
        """Idempotently configure logging in a thread-safe manner.

        Uses ``logging.config.dictConfig`` so it works natively with Django's
        ``LOGGING`` setting.  Does **not** mutate the global
        ``LogRecordFactory`` or call ``basicConfig()``.  Safe to call
        multiple times — subsequent calls return the existing logger unless
        *force_reconfigure* is ``True``.

        All arguments are keyword-only.  Pass only what you want to override —
        :meth:`LoggingConfig.build` fills in opinionated defaults for
        everything omitted or left as ``None``.

        Args:
            root_logger_name: Name for the root application logger (required).
            level: Log level. Defaults to ``VERBOSE`` (or ``DEFAULT_LOG_LEVEL`` env-var).
            file: Path to a log file. Optional suffix; datestamp appended when omitted.
            fmt: Log format string. Defaults to :attr:`AppLogger.DEFAULT_FORMAT`.
            enable_color: Enable coloredlogs output. Defaults to TTY detection.
            isatty: Override TTY detection used by *enable_color*.
            use_json: Emit JSON log records instead of plain text. Default ``False``.
            configure_root: Configure the root logger (``True``) or only the named
                logger (``False``, useful inside libraries). Default ``True``.
            update_loggers: Map of ``{logger_name: level}`` overrides for third-party
                loggers (e.g. ``{"django": logging.WARNING}``).
            enable_otel_correlation: Inject OTel trace/span IDs. Default ``False``.
            otel_optional: Suppress ``ImportError`` when ``opentelemetry`` is absent.
                Default ``True``.
            field_styles: coloredlogs field styles merged over coloredlogs defaults.
            level_styles: coloredlogs level styles merged over coloredlogs defaults.
            force_reconfigure: Re-run configuration even if already configured.
                Default ``False``.

        Returns:
            The root :class:`AppLogger` named *root_logger_name*.

        Example::

            logger = AppLogger.initialize(
                root_logger_name="orders",
                level=AppLogger.DEBUG,
                file="logs/orders",
                enable_color=True,
            )
        """
        _config = LoggingConfig.build(
            root_logger_name=root_logger_name,
            level=level,
            file=file,
            fmt=fmt,
            enable_color=enable_color,
            isatty=isatty,
            use_json=use_json,
            configure_root=configure_root,
            update_loggers=update_loggers,
            enable_otel_correlation=enable_otel_correlation,
            otel_optional=otel_optional,
            field_styles=field_styles,
            level_styles=level_styles,
        )

        with AppLogger._config_lock:
            if AppLogger._configured and not force_reconfigure:
                return AppLogger.get_logger(_config.root_logger_name)

            AppLogger._register_levels_and_class()

            # Resolve log file
            file_path: str | None = None
            if _config.file:
                path = Path(_config.file)
                if not path.suffix:
                    path = (
                        path.parent
                        / f"{path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
                    )
                path.parent.mkdir(parents=True, exist_ok=True)
                file_path = str(path)
                AppLogger.LOG_FILE = path

            AppLogger._configure_logging(_config, file_path)

            # Coloredlogs
            if _config.enable_color and _config.isatty and not _config.use_json:
                _try_enable_coloredlogs(_config)

            # OpenTelemetry correlation
            if _config.enable_otel_correlation:
                _enable_otel_log_correlation(optional=_config.otel_optional)

            AppLogger._configured = True

            logger = AppLogger.get_logger(_config.root_logger_name)
            logger.notice(
                "App Logger Configured -> {} | {}",
                logging.getLevelName(_config.level),
                file_path,
            )
            return logger

    @classmethod
    def get_logger(cls, name: str) -> AppLogger:
        """Return an :class:`AppLogger` registered under *name*.

        Ensures :class:`AppLogger` is registered as the logger class before
        creating the logger, so callers never receive a plain
        :class:`logging.Logger` instance even when :meth:`initialize` has not
        yet been called.

        For best results call :meth:`initialize` early (``main()``,
        ``wsgi.py``, ``AppConfig.ready()``).
        """
        cls._register_levels_and_class()
        return cast(AppLogger, logging.getLogger(name))

    # -- level management --------------------------------------------------

    def update_level(self, level: int) -> None:
        """Temporarily change this logger and all root handlers to *level*.

        Does nothing when *level* equals the logger's initial level.

        Args:
            level: The new log level (e.g. :data:`logging.DEBUG`).
        """
        if level == self._init_level:
            return
        self.info("Updating Log Level -> {} -> {}", self._init_level, level)
        self.setLevel(level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(level)

    def restore_level(self) -> None:
        """Revert this logger and all root handlers to the level set at construction.

        Does nothing when the current level already matches the initial level.
        """
        if self.level == self._init_level:
            return
        self.info("Restoring Log Level -> {} -> {}", self.level, self._init_level)
        self.setLevel(self._init_level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(self._init_level)

    # -- trace -------------------------------------------------------------

    # NOSONAR(python:S1845): these method names intentionally match the
    # stdlib logging.Logger / verboselogs.VerboseLogger API (and the
    # same-named level constants above) — that's the entire point of
    # subclassing them. Renaming would break drop-in compatibility.

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``CRITICAL`` level."""
        super().critical(msg, *args, **kwargs)

    def fatal(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``FATAL`` level."""
        super().fatal(msg, *args, **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``ERROR`` level."""
        super().error(msg, *args, **kwargs)

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a message with exception context at the ``ERROR`` level."""
        kwargs.setdefault("exc_info", True)
        super().exception(msg, *args, **kwargs)

    def success(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``SUCCESS`` level."""
        super().success(msg, *args, **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``WARNING`` level."""
        super().warning(msg, *args, **kwargs)

    def notice(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``NOTICE`` level."""
        super().notice(msg, *args, **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``INFO`` level."""
        super().info(msg, *args, **kwargs)

    def verbose(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``VERBOSE`` level."""
        super().verbose(msg, *args, **kwargs)

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``DEBUG`` level."""
        super().debug(msg, *args, **kwargs)

    def spam(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``SPAM`` level."""
        super().spam(msg, *args, **kwargs)

    def trace(self, msg: Any, *args: Any, **kwargs: Any) -> None:  # NOSONAR
        """Log a message at the ``TRACE`` level."""
        self.log(TRACE, msg, *args, **kwargs)

    # -- audit decorators --------------------------------------------------

    def audit_method(
        self,
        *,
        exclude: list[str] | None = None,
        include: list[str] | None = None,
        level: int | None = None,
        log_return_value: bool = False,
    ):
        """Decorator that logs method entry (with args) and exit (with timing).

        Args:
            exclude: Parameter names to omit from the entry log.
                ``self`` and ``cls`` are always excluded automatically.
            include: When provided, only these parameter names are logged.
            level: Logging level for audit messages.
                Defaults to the ``AUDIT_LOG_LEVEL`` env-var (default ``SPAM``).
            log_return_value: When ``True``, log the return value after the call.
                Avoid for methods that return large objects or lazy iterables.

        Example::

            logger = AppLogger.get_logger(__name__)

            @logger.audit_method(exclude=["password"])
            def authenticate(user: str, password: str) -> bool:
                ...
        """

        def decorator(func: Any) -> Any:
            return self._wrap_audited(
                func, exclude or [], include or [], level, log_return_value
            )

        return decorator

    def audit_class(
        self,
        *,
        exclude: list[str] | None = None,
        include: list[str] | None = None,
        include_inherited: bool = False,
        level: int | None = None,
        log_return_value: bool = False,
    ):
        """Class decorator that applies :meth:`audit_method` to every public method.

        Skips private (``_``-prefixed) and dunder (``__``-prefixed) methods.
        Set ``include_inherited=True`` to wrap public methods inherited from base
        classes as well.

        Example::

            logger = AppLogger.get_logger(__name__)

            @logger.audit_class(exclude=["token"])
            class Client:
                def fetch(self, token: str, resource_id: str) -> dict[str, Any]:
                    ...
        """
        _exclude = exclude or []
        _include = include or []

        def decorator(cls: type) -> type:
            members = AppLogger._collect_auditable_members(cls, include_inherited)
            for attr_name, attr_value in members:
                if not self._should_audit_member(attr_name, _exclude, _include):
                    continue
                setattr(
                    cls,
                    attr_name,
                    self._wrap_audited(
                        attr_value, _exclude, _include, level, log_return_value
                    ),
                )
            return cls

        return decorator

    @staticmethod
    def _collect_auditable_members(
        target_cls: type, include_inherited: bool
    ) -> list[tuple[str, Any]]:
        if include_inherited:
            return inspect.getmembers(target_cls, predicate=inspect.isfunction)
        return [
            (attr_name, attr_value)
            for attr_name, attr_value in target_cls.__dict__.items()
            if inspect.isfunction(attr_value)
        ]

    @staticmethod
    def _should_audit_member(
        attr_name: str, exclude: list[str], include: list[str]
    ) -> bool:
        if attr_name.startswith("_"):
            return False
        if include and attr_name not in include:
            return False
        return attr_name not in exclude

    def _wrap_audited(
        self,
        func: Any,
        exclude: list[str],
        include: list[str],
        level: int | None,
        log_return_value: bool,
    ) -> Any:
        audit_level = level or self._audit_level
        sep = self._audit_separator

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = ReflectUtils.get_fully_qualified_name(func)
            logger = AppLogger.get_logger(func.__module__)

            AppLogger._log_audit_enter(
                logger,
                func,
                func_name,
                args,
                kwargs,
                exclude,
                include,
                audit_level,
                sep,
            )

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                elapsed = time.perf_counter() - start
                AppLogger._log_audit_error(logger, func_name, exc, elapsed, audit_level)
                raise

            elapsed = time.perf_counter() - start
            AppLogger._log_audit_exit(
                logger, func_name, result, elapsed, audit_level, sep, log_return_value
            )
            return result

        return wrapper

    @staticmethod
    def _log_audit_enter(
        logger: AppLogger,
        func: Any,
        func_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        exclude: list[str],
        include: list[str],
        audit_level: int,
        sep: str,
    ) -> None:
        if not logger.isEnabledFor(audit_level):
            return
        try:
            formatted_args = _format_arguments(func, args, kwargs, exclude, include)
            logger.log(
                audit_level,
                "Enter -> {}",
                sep.join(formatted_args) if formatted_args else "<empty>",
                extra={"caller": func_name},
            )
        except Exception as log_exc:
            logger.warning(
                "audit_entry_error: {} | {}",
                func_name,
                f"{type(log_exc).__qualname__}: {log_exc}",
            )

    @staticmethod
    def _log_audit_error(
        logger: AppLogger,
        func_name: str,
        exc: Exception,
        elapsed: float,
        audit_level: int,
    ) -> None:
        if not getattr(exc, "_audit_logged", False):
            setattr(exc, "_audit_logged", True)
            logger.log(
                audit_level,
                "Error -> {} | Time={:.6f} | {}",
                func_name,
                elapsed,
                f"{type(exc).__qualname__}: {exc}",
                extra={"caller": func_name},
                exc_info=True,
            )
        else:
            logger.log(
                audit_level,
                "Error -> {} | Time={:.6f} | re-raised {}",
                func_name,
                elapsed,
                type(exc).__qualname__,
                extra={"caller": func_name},
            )

    @staticmethod
    def _log_audit_exit(
        logger: AppLogger,
        func_name: str,
        result: Any,
        elapsed: float,
        audit_level: int,
        sep: str,
        log_return_value: bool,
    ) -> None:
        if log_return_value and logger.isEnabledFor(audit_level):
            logger.log(
                audit_level,
                "ReturnValue -> {}",
                result,
                extra={"caller": func_name},
            )

        if logger.isEnabledFor(audit_level):
            logger.log(
                audit_level,
                "Exit -> {}",
                sep.join(
                    [
                        f"Time={elapsed:.6f}",
                        f"type={type(result).__qualname__}",
                    ]
                ),
                extra={"caller": func_name},
            )

    # -- variable inspection helpers ---------------------------------------

    def debug_variables(self, var_names: str, message: str | None = None) -> None:
        """Log one or more variables by name at ``DEBUG`` level.

        Variable values are resolved from the caller's frame at call time.

        Args:
            var_names: Comma-separated string of variable names to resolve,
                e.g. ``"request, user_id"``.
            message: Optional label prepended to the output. Defaults to
                ``"Variables"``.

        Example::

            logger.debug_variables("request_id, payload.order_id")
        """
        self._log_variables(var_names, message, level=logging.DEBUG)

    def trace_variables(self, var_names: str, message: str | None = None) -> None:
        """Log one or more variables by name at ``TRACE`` level.

        Variable values are resolved from the caller's frame at call time.

        Args:
            var_names: Comma-separated string of variable names to resolve,
                e.g. ``"payload, headers"``.
            message: Optional label prepended to the output. Defaults to
                ``"Variables"``.

        Example::

            logger.trace_variables("response.status_code, response.headers")
        """
        self._log_variables(var_names, message, level=TRACE)

    def _log_variables(
        self,
        var_names: str,
        message: str | None,
        level: int,
    ) -> None:
        if not self.isEnabledFor(level):
            return
        # Walk up: inspect.currentframe() → _log_variables → debug/trace_variables → caller
        _f = inspect.currentframe()
        _f = _f.f_back.f_back if _f is not None and _f.f_back is not None else None
        resolved = _resolve_variables(var_names, _f)
        self.log(
            level,
            "{} -> {}",
            message or "Variables",
            self._audit_separator.join(resolved),
        )

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _register_levels_and_class() -> None:
        """Register TRACE level, AppLogger as the logger class, and BraceLogRecord factory (idempotent)."""
        if not hasattr(logging, "TRACE"):
            logging.addLevelName(TRACE, "TRACE")
            setattr(logging, "TRACE", TRACE)
        if logging.getLoggerClass() is not AppLogger:
            logging.setLoggerClass(AppLogger)
        if logging.getLogRecordFactory() is not BraceLogRecord:
            logging.setLogRecordFactory(BraceLogRecord)

    @staticmethod
    def _configure_logging(config: LoggingConfig, file_path: str | None) -> None:
        """Build and apply a ``logging.config.dictConfig``-compatible dict.

        ``fmt`` and ``update_loggers`` are already fully resolved on *config*
        by :meth:`LoggingConfig.build`.
        """
        filters: dict[str, Any] = {
            "enrich": {
                "()": EnrichFilter,
                "service_name": config.root_logger_name,
                "environment": None,
                "inject_otel_defaults": config.enable_otel_correlation,
            }
        }

        if config.use_json:
            formatter_name = "json"
            formatters: dict[str, Any] = {
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "fmt": (
                        "%(asctime)s %(levelname)s %(name)s %(service)s %(env)s "
                        "%(caller)s %(message)s %(otelTraceID)s %(otelSpanID)s "
                        "%(otelTraceSampled)s"
                    ),
                }
            }
        else:
            formatter_name = "standard"
            formatters = {"standard": {"format": config.fmt}}

        handlers: dict[str, Any] = {
            "console": {
                "class": "logging.StreamHandler",
                "level": config.level,
                "formatter": formatter_name,
                "filters": ["enrich"],
                "stream": "ext://sys.stdout",
            }
        }

        if file_path:
            handlers["file"] = {
                "class": "logging.FileHandler",
                "level": config.level,
                "formatter": formatter_name,
                "filters": ["enrich"],
                "filename": file_path,
            }

        handler_names = ["console"] + (["file"] if file_path else [])

        # Third-party logger level overrides — baked into dictConfig for atomic application
        extra_loggers: dict[str, Any] = {
            name: {"level": lvl, "propagate": True}
            for name, lvl in config.update_loggers.items()
        }

        if config.configure_root:
            root: dict[str, Any] = {"handlers": handler_names, "level": config.level}
            loggers: dict[str, Any] = extra_loggers
        else:
            root = {"handlers": [], "level": "WARNING"}
            loggers = {
                config.root_logger_name: {
                    "handlers": handler_names,
                    "level": config.level,
                    "propagate": False,
                },
                **extra_loggers,
            }

        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "filters": filters,
                "formatters": formatters,
                "handlers": handlers,
                "root": root,
                "loggers": loggers,
            }
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _try_enable_coloredlogs(config: LoggingConfig) -> None:
    """Install coloredlogs with styles merged over coloredlogs defaults.

    Silently no-ops when ``coloredlogs`` is not installed or installation fails —
    coloredlogs is a best-effort enhancement, never a hard requirement.
    """
    try:
        import coloredlogs
    except ImportError:
        return

    try:
        coloredlogs.install(  # pyright: ignore[reportUnknownMemberType]  # coloredlogs lacks stubs
            level=config.level,
            field_styles={**coloredlogs.DEFAULT_FIELD_STYLES, **config.field_styles},
            level_styles={**coloredlogs.DEFAULT_LEVEL_STYLES, **config.level_styles},
        )
    except Exception:
        return


def _enable_otel_log_correlation(*, optional: bool) -> None:
    """Inject OTel trace/span IDs into log records."""
    try:
        module = importlib.import_module("opentelemetry.instrumentation.logging")
        instrumentor_cls = module.LoggingInstrumentor
    except Exception:
        if optional:
            return
        raise

    try:
        instrumentor_cls().instrument(set_logging_format=False)
    except Exception:
        if optional:
            return
        raise


def _format_arguments(
    func: object,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    exclude: list[str],
    include: list[str],
) -> list[str]:
    """Format function call arguments as ``name=value`` strings.

    ``self`` and ``cls`` are always excluded.
    """
    try:
        sig = inspect.signature(func)  # pyright: ignore[reportArgumentType]
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
    except TypeError, ValueError:
        return [repr(args), repr(kwargs)]

    parts: list[str] = []
    for name, value in bound.arguments.items():
        if name in _AUDIT_SELF_PARAMS:
            continue
        if include and name not in include:
            continue
        if name in exclude:
            continue
        parts.append(f"{name}={value!r}")
    return parts


def _resolve_variables(var_names: str, frame: FrameType | None) -> list[str]:
    """Resolve comma-separated variable names from a stack frame.

    Supports dot-notation for attribute traversal (e.g. ``"obj.attr"``).
    Callable leaf attributes are called with no arguments.
    """
    if frame is None or not hasattr(frame, "f_locals"):
        return [f"<cannot resolve: {var_names}>"]
    local_vars = frame.f_locals
    global_vars = frame.f_globals
    parts: list[str] = []
    for name in (n.strip() for n in var_names.split(",")):
        if "." in name:
            parts.append(_resolve_dotted_variable(name, local_vars, global_vars))
        elif name in local_vars:
            parts.append(f"{name}={local_vars[name]!r}")
        elif name in global_vars:
            parts.append(f"{name}={global_vars[name]!r}")
        else:
            parts.append(f"{name}=<undefined>")
    return parts


def _resolve_dotted_variable(
    name: str, local_vars: dict[str, Any], global_vars: dict[str, Any]
) -> str:
    root, _, rest = name.partition(".")
    if root in local_vars:
        root_val = local_vars[root]
    elif root in global_vars:
        root_val = global_vars[root]
    else:
        return f"{name}=<undefined>"

    try:
        val = _attrgetter(rest)(root_val)
        if callable(val):
            val = val()
        return f"{name}={val!r}"
    except AttributeError:
        return f"{name}=<undefined>"


__all__ = [
    "TRACE",
    "AppLogger",
    "BraceLogRecord",
    "EnrichFilter",
    "LoggingConfig",
]
