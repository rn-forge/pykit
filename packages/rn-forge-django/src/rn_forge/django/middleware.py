"""WSGI middleware emitting one access-log event per request."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from rn_forge.commons.logging import AppLogger
from rn_forge.web import request_log_fields

__all__ = ["AccessLogMiddleware"]

_LOGGER = AppLogger.get_logger(__name__)

type Log = Callable[[str, Mapping[str, Any]], None]


class AccessLogMiddleware:
    """Time each request and emit one ``request.complete`` access-log event.

    Tracing is W3C Trace Context, propagated and read through OpenTelemetry
    (:mod:`rn_forge.web.tracing`) — this middleware carries no header
    handling. ``rn_forge.django.tracing.instrument()`` inserts
    `DjangoInstrumentor`'s own middleware at position 0 in ``MIDDLEWARE``,
    which wraps this one and everything downstream.

    Args:
        get_response: The next layer, as Django passes it.
        log: Replaces :meth:`log` — for programmatic construction and tests.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponseBase],
        *,
        log: Log | None = None,
    ) -> None:
        self.get_response = get_response
        self._log: Log = log if log is not None else self.log

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        started = time.perf_counter()
        response = self.get_response(request)
        self._log(
            "request.complete",
            request_log_fields(
                method=request.method or "",
                path=request.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            ),
        )
        return response

    def log(self, event: str, context: Mapping[str, Any]) -> None:
        """Log *event* through ``AppLogger`` at info, as ``key=value`` pairs."""
        _LOGGER.info(
            "{} {}", event, " ".join(f"{key}={value}" for key, value in context.items())
        )
