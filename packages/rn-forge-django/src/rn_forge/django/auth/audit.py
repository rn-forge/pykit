"""Audit events of the auth surface, on one :class:`AppLogger` channel.

An event is one ``INFO`` record on the ``rn_forge.audit.auth`` logger:
``audit event=<name> key='value' ...``. Fields are account IDs, provider IDs,
codes and short reasons; callers never pass a token, code, assertion, password
or email address.
"""

from __future__ import annotations

from typing import Final

from rn_forge.commons.logging import AppLogger

__all__ = ["AUDIT_LOGGER", "audit"]

AUDIT_LOGGER: Final = "rn_forge.audit.auth"
_CHANNEL: Final = AppLogger.get_logger(AUDIT_LOGGER)


def audit(event: str, **fields: object) -> None:
    """Record the audit event *event* with *fields*; ``None`` fields are left out."""
    detail = " ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)
    _CHANNEL.info("audit event={} {}", event, detail)  # brace-style log format
