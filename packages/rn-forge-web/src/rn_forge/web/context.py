"""The correlation ID: a per-request identifier that survives service hops.

The smallest module in the package and the one everything else reads. It holds
a :class:`~contextvars.ContextVar` and the four functions around it, plus a
structlog-shaped log processor that injects the bound value.

Two ways to bind, and the difference matters
--------------------------------------------

:func:`set_correlation_id` binds without keeping a reset token.
:func:`bind_correlation_id` is a context manager that resets on exit. They are
not interchangeable, and the next person to read this will want to "fix" one
into the other:

- **ASGI (use** :func:`set_correlation_id` **).** Every request runs in its own
  task with its own copied context, so leaving the value bound leaks nothing
  into another request. It must *not* be reset in a ``finally``, because a bare
  ``Exception`` handler is dispatched by the server's outermost error
  middleware — which sits outside every user-added middleware — so resetting on
  the way out unbinds the value before the handler that needs it runs.
- **WSGI / sync (use** :func:`bind_correlation_id` **).** A worker thread
  genuinely is reused across requests, so the binding must be undone or the
  next request on that thread inherits it.

The log processor is duck-typed
-------------------------------

:func:`correlation_log_processor` has structlog's processor signature — three
positional arguments returning the event dict — but this module does not import
structlog. That is deliberate boundary-keeping rather than dependency
avoidance: this package must stay importable in a process that has no
structlog, and the signature is three positional arguments wide.
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
"""The header name every ``rn-forge-*`` application reads and writes.

``X-Correlation-ID`` rather than ``X-Request-ID`` because it is the name that
survives across service hops, which is the actual use case. It is a parameter
everywhere it is read, for deployments fronted by infrastructure that stamps a
different header.
"""

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

    This is the ASGI form. See the module docstring for why it deliberately
    does not reset.
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

    Usable directly as ``structlog.configure(processors=[correlation_log_processor, ...])``.
    The signature is duck-typed against structlog's processor protocol, not an
    import of it — see the module docstring.

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
