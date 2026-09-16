"""Store and propagate a request correlation ID.

Use :func:`set_correlation_id` for task-local ASGI contexts and
:func:`bind_correlation_id` where a reused worker context must be reset.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

from rn_forge.web.exceptions import WebError

__all__ = [
    "DEFAULT_CORRELATION_HEADER",
    "bind_correlation_id",
    "correlation_id_var",
    "correlation_log_processor",
    "get_correlation_id",
    "new_correlation_id",
    "require_correlation_id",
    "set_correlation_id",
]

DEFAULT_CORRELATION_HEADER: Final = "X-Correlation-ID"
"""Default request and response header for correlation IDs."""

CORRELATION_ID_KEY: Final = "correlation_id"
"""The key :func:`correlation_log_processor` writes, and the problem-body extension name."""

correlation_id_var: ContextVar[str | None] = ContextVar(
    "rn_forge_correlation_id", default=None
)
"""The bound correlation ID, or ``None`` outside a request."""


def new_correlation_id() -> str:
    """Return a fresh correlation ID (a UUID4 hex string)."""
    return uuid.uuid4().hex


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
