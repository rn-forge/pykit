"""The WSGI correlation-ID middleware.

The ContextVar, its accessors and the structlog processor are
:mod:`rn_forge.web.context`'s; this module binds the variable for the length of
a Django request and nothing else. Read the bound value with
:func:`rn_forge.web.get_correlation_id`.

It binds with :func:`rn_forge.web.bind_correlation_id`, **the form that resets
on exit**: a WSGI worker thread is reused across requests, so a value left bound
leaks into the next one. (The ASGI middleware in ``rn_forge.web`` deliberately
does not reset; do not copy that half here.)

Put it **first** in ``MIDDLEWARE`` so everything downstream — including the
problem-details exception handler — sees the binding::

    MIDDLEWARE = ["rn_forge.django.middleware.CorrelationIdMiddleware", ...]

Customization is by subclassing, since ``MIDDLEWARE`` names a class: set
``header`` for infrastructure that stamps a different header, and override
:meth:`CorrelationIdMiddleware.log` to send ``request.complete`` somewhere other
than ``AppLogger``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from rn_forge.commons.logging import AppLogger
from rn_forge.web import DEFAULT_CORRELATION_HEADER, bind_correlation_id

__all__ = ["CorrelationIdMiddleware"]

_LOGGER = AppLogger.get_logger(__name__)

type Log = Callable[[str, Mapping[str, Any]], None]


class CorrelationIdMiddleware:
    """Assign and propagate a correlation ID for every request.

    Reads the inbound header, or generates an ID when it is absent or blank;
    binds it for the request and as ``request.correlation_id``; echoes it on the
    response; and emits one ``request.complete`` event carrying ``method``,
    ``path``, ``status``, ``duration_ms`` and ``correlation_id``.

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
        inbound = request.headers.get(self._header) or None
        with bind_correlation_id(inbound) as correlation_id:
            setattr(request, "correlation_id", correlation_id)  # noqa: B010 - HttpRequest declares no such attribute
            response = self.get_response(request)
            response[self._header] = correlation_id
            self._log(
                "request.complete",
                {
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "correlation_id": correlation_id,
                },
            )
            return response

    def log(self, event: str, context: Mapping[str, Any]) -> None:
        """Log *event* through ``AppLogger`` at info, as ``key=value`` pairs."""
        _LOGGER.info(
            "{} {}", event, " ".join(f"{key}={value}" for key, value in context.items())
        )
