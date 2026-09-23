"""Store and propagate a request correlation ID.

Use :func:`set_correlation_id` for task-local ASGI contexts and
:func:`bind_correlation_id` where a reused worker context must be reset.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Generator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

from rn_forge.web.exceptions import WebError

__all__ = [
    "DEFAULT_CORRELATION_HEADER",
    "EXPOSED_HEADERS",
    "MAX_CORRELATION_ID_LENGTH",
    "bind_correlation_id",
    "correlation_id_var",
    "correlation_log_processor",
    "get_correlation_id",
    "is_valid_correlation_id",
    "new_correlation_id",
    "request_log_fields",
    "require_correlation_id",
    "resolve_correlation_id",
    "set_correlation_id",
]

DEFAULT_CORRELATION_HEADER: Final = "X-Correlation-ID"
"""Default request and response header for correlation IDs."""

CORRELATION_ID_KEY: Final = "correlation_id"
"""The key :func:`correlation_log_processor` writes, and the problem-body extension name."""

MAX_CORRELATION_ID_LENGTH: Final = 128
"""The longest correlation ID :func:`is_valid_correlation_id` accepts."""

EXPOSED_HEADERS: Final[tuple[str, ...]] = (
    "ETag",
    "Link",
    "Location",
    DEFAULT_CORRELATION_HEADER,
    "Retry-After",
    "Deprecation",
    "Sunset",
)
"""Response headers this kit emits that a browser can read only when a CORS
policy names them in ``Access-Control-Expose-Headers``.

An application's own CORS configuration does not know what the kit emits; a
CORS binding passes this list so the kit's own concurrency, discovery and
retry contracts survive a browser client.
"""

_CORRELATION_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._:-]+$")


def is_valid_correlation_id(value: str) -> bool:
    """Return whether *value* is a well-formed correlation ID.

    True for 1–:data:`MAX_CORRELATION_ID_LENGTH` characters of
    ``[A-Za-z0-9._:-]``.
    """
    return (
        1 <= len(value) <= MAX_CORRELATION_ID_LENGTH
        and _CORRELATION_ID_PATTERN.match(value) is not None
    )


correlation_id_var: ContextVar[str | None] = ContextVar(
    "rn_forge_correlation_id", default=None
)
"""The bound correlation ID, or ``None`` outside a request."""


def new_correlation_id() -> str:
    """Return a fresh correlation ID (a UUID4 hex string)."""
    return uuid.uuid4().hex


def resolve_correlation_id(
    inbound: str | None,
    *,
    validator: Callable[[str], bool] = is_valid_correlation_id,
    generator: Callable[[], str] = new_correlation_id,
) -> str:
    """Return the correlation ID to bind for a request.

    A well-formed caller-supplied ID is kept verbatim; an absent or malformed
    one is replaced by *generator*, never sanitized.

    Args:
        inbound: The request header's value, or ``None`` when absent.
        validator: Returns whether a caller-supplied ID is well-formed.
        generator: Produces a fresh ID.
    """
    return inbound if inbound is not None and validator(inbound) else generator()


def set_correlation_id(value: str) -> None:
    """Bind *value* for the current context, keeping no reset token.

    Use this form when the caller owns an isolated task context.
    """
    correlation_id_var.set(value)


def get_correlation_id() -> str | None:
    """Return the bound correlation ID, or ``None`` when nothing is bound."""
    return correlation_id_var.get()


def require_correlation_id() -> str:
    """Return the bound correlation ID.

    Raises:
        WebError: Nothing is bound in the current context.
    """
    value = correlation_id_var.get()
    if value is None:
        raise WebError("No correlation ID is bound in the current context")
    return value


@contextmanager
def bind_correlation_id(value: str | None = None) -> Generator[str]:
    """Bind a correlation ID for the duration of the block, resetting on exit.

    This is the WSGI/sync form: a worker thread is reused across requests, so
    the binding must be undone — including when the block raises.

    Args:
        value: The ID to bind. When ``None``, a fresh one is generated.

    Yields:
        The bound correlation ID.
    """
    bound = value if value is not None else new_correlation_id()
    token = correlation_id_var.set(bound)
    try:
        yield bound
    finally:
        correlation_id_var.reset(token)


def request_log_fields(
    *,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    correlation_id: str | None,
) -> dict[str, Any]:
    """Return one access-log event's fields.

    Method, path and status follow the OpenTelemetry HTTP semantic
    conventions' attribute names, so a log pipeline and a trace span agree on
    what to call them.

    Args:
        method: The request method.
        path: The request path.
        status: The response status code.
        duration_ms: How long the request took, in milliseconds.
        correlation_id: The bound correlation ID, or ``None``.

    Returns:
        ``http.request.method``, ``url.path``, ``http.response.status_code``,
        ``duration_ms``, ``correlation_id``.
    """
    return {
        "http.request.method": method,
        "url.path": path,
        "http.response.status_code": status,
        "duration_ms": duration_ms,
        CORRELATION_ID_KEY: correlation_id,
    }


def correlation_log_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject the bound correlation ID into a structlog event dict.

    Usable directly as a structlog processor without importing structlog.

    Args:
        logger: The bound logger. Unused; part of the processor signature.
        method_name: The log method's name. Unused; part of the signature.
        event_dict: The event dictionary, mutated in place and returned.

    Returns:
        *event_dict*, with ``correlation_id`` set when one is bound and left
        untouched when none is.
    """
    del logger, method_name
    value = correlation_id_var.get()
    if value is not None:
        event_dict[CORRELATION_ID_KEY] = value
    return event_dict
