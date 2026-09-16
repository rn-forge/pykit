"""Structlog context binding over :class:`AppLogger` handlers.

Use :meth:`~rn_forge.commons.logging.logger.AppLogger.get_logger` directly for
unstructured logging. :class:`StructLogger` binds context carried across a
chain of calls while retaining the configured Rich, file, or JSON handlers.

**Call** :meth:`~rn_forge.commons.logging.logger.AppLogger.initialize` **before the
first** :class:`StructLogger` **log call** (not necessarily before
constructing one — the underlying logger is resolved lazily, on first use).
The custom ``TRACE``, ``SPAM``, ``VERBOSE``, ``NOTICE``, and ``SUCCESS`` levels
are available alongside the standard levels.

Requires the ``structlog`` extra — this module is not imported by
``rn_forge.commons``'s curated ``__init__.py``, so ``import rn_forge.commons``
never requires it.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Self

import structlog

from rn_forge.commons.logging.logger import AppLogger

__all__ = ["StructLogger"]

_configured = False


def _app_logger_factory(*args: Any) -> AppLogger:
    """Return the named :class:`AppLogger` for structlog."""
    return AppLogger.get_logger(args[0] if args else __name__)


def _render_event(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> str:
    """Render an event and its context as an :class:`AppLogger` message."""
    event = str(event_dict.pop("event", ""))
    context = " | ".join(
        f"{key}={value!r}" for key, value in sorted(event_dict.items())
    )
    return f"{event} | {context}" if context else event


class _AppBoundLogger(structlog.stdlib.BoundLogger):
    """Add verboselogs' custom level methods to a bound logger."""

    def trace(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        return self._proxy_to_logger("trace", event, *args, **kw)

    def spam(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        return self._proxy_to_logger("spam", event, *args, **kw)

    def verbose(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        return self._proxy_to_logger("verbose", event, *args, **kw)

    def notice(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        return self._proxy_to_logger("notice", event, *args, **kw)

    def success(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        return self._proxy_to_logger("success", event, *args, **kw)


def _configure_once() -> None:
    """Configure structlog exactly once per process.

    Deliberately does **not** use ``structlog.stdlib.LoggerFactory`` — its
    constructor calls ``logging.setLoggerClass()``, clobbering
    ``AppLogger``'s own registration. ``_app_logger_factory`` resolves loggers
    through ``AppLogger.get_logger`` directly instead.
    """
    global _configured
    if _configured:
        return
    structlog.configure(
        processors=[structlog.contextvars.merge_contextvars, _render_event],
        logger_factory=_app_logger_factory,
        wrapper_class=_AppBoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


class StructLogger:
    """Structlog front end over :class:`AppLogger` handlers.

    Bound context and structured fields flow through the handlers configured by
    :meth:`AppLogger.initialize`.
    """

    def __init__(self, name: str, **initial_context: Any) -> None:
        """Initialize :class:`StructLogger`, bound to *name* with *initial_context*."""
        _configure_once()
        self._bound: _AppBoundLogger = structlog.get_logger(name).bind(
            **initial_context
        )

    @classmethod
    def _wrapping(cls, bound: _AppBoundLogger) -> Self:
        instance = cls.__new__(cls)
        instance._bound = bound
        return instance

    def bind(self, **new_context: Any) -> Self:
        """Return a new :class:`StructLogger` with *new_context* merged in."""
        return self._wrapping(self._bound.bind(**new_context))

    def unbind(self, *keys: str) -> Self:
        """Return a new :class:`StructLogger` with *keys* removed from its bound context."""
        return self._wrapping(self._bound.unbind(*keys))

    def new(self, **context: Any) -> Self:
        """Return a new :class:`StructLogger` with its context reset to *context*."""
        return self._wrapping(self._bound.new(**context))

    @property
    def structlog(self) -> structlog.stdlib.BoundLogger:
        """The underlying ``structlog.stdlib.BoundLogger``."""
        return self._bound

    def trace(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``TRACE`` level with *kwargs* as structured fields."""
        self._bound.trace(event, **kwargs)

    def spam(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``SPAM`` level with *kwargs* as structured fields."""
        self._bound.spam(event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``DEBUG`` level with *kwargs* as structured fields."""
        self._bound.debug(event, **kwargs)

    def verbose(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``VERBOSE`` level with *kwargs* as structured fields."""
        self._bound.verbose(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``INFO`` level with *kwargs* as structured fields."""
        self._bound.info(event, **kwargs)

    def notice(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``NOTICE`` level with *kwargs* as structured fields."""
        self._bound.notice(event, **kwargs)

    def success(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``SUCCESS`` level with *kwargs* as structured fields."""
        self._bound.success(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``WARNING`` level with *kwargs* as structured fields."""
        self._bound.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``ERROR`` level with *kwargs* as structured fields."""
        self._bound.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log *event* at the ``CRITICAL`` level with *kwargs* as structured fields."""
        self._bound.critical(event, **kwargs)
