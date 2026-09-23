"""WSGI middleware for binding and propagating correlation IDs."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from rn_forge.commons.logging import AppLogger
from rn_forge.web import (
    DEFAULT_CORRELATION_HEADER,
    bind_correlation_id,
    request_log_fields,
    resolve_correlation_id,
)

__all__ = ["CorrelationIdMiddleware"]

_LOGGER = AppLogger.get_logger(__name__)

type Log = Callable[[str, Mapping[str, Any]], None]


class CorrelationIdMiddleware:
    """Assign and propagate a correlation ID for every request.

    Place it first in ``MIDDLEWARE`` so downstream code sees the binding. A
    caller-supplied ID is kept when well-formed and replaced otherwise
    (:func:`rn_forge.web.resolve_correlation_id`). The response echoes the ID
    and a ``request.complete`` event records the result.

    Args:
        get_response: The next layer, as Django passes it.
        log: Replaces :meth:`log` — for programmatic construction and tests.
        header: Replaces the ``header`` class attribute.
    """

    header: ClassVar[str] = DEFAULT_CORRELATION_HEADER

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponseBase],
        *,
        log: Log | None = None,
        header: str | None = None,
    ) -> None:
        self.get_response = get_response
        self._log: Log = log if log is not None else self.log
        self._header = header if header is not None else self.header

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        started = time.perf_counter()
        inbound = resolve_correlation_id(request.headers.get(self._header))
        with bind_correlation_id(inbound) as correlation_id:
            setattr(request, "correlation_id", correlation_id)  # noqa: B010 - HttpRequest declares no such attribute
            response = self.get_response(request)
            response[self._header] = correlation_id
            self._log(
                "request.complete",
                request_log_fields(
                    method=request.method or "",
                    path=request.path,
                    status=response.status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    correlation_id=correlation_id,
                ),
            )
            return response

    def log(self, event: str, context: Mapping[str, Any]) -> None:
        """Log *event* through ``AppLogger`` at info, as ``key=value`` pairs."""
        _LOGGER.info(
            "{} {}", event, " ".join(f"{key}={value}" for key, value in context.items())
        )
