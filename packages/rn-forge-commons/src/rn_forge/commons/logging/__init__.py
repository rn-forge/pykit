"""Logging mechanisms: the configured stdlib front end and its structlog façade.

:mod:`~rn_forge.commons.logging.logger` owns process-wide initialisation and the
:class:`AppLogger` every package logs through; :mod:`~rn_forge.commons.logging.structlog`
(behind the ``structlog`` extra) binds context on top of the same handlers.
:mod:`~rn_forge.commons.logging.redaction` replaces secrets in log values.

The curated names below are re-exported from :mod:`rn_forge.commons` as well.
"""

from __future__ import annotations

from rn_forge.commons.logging.logger import (
    TRACE,
    AppLogger,
    BraceLogRecord,
    EnrichFilter,
    LoggingConfig,
    RedactFilter,
)
from rn_forge.commons.logging.redaction import REDACTED, RedactionPolicy, redact

__all__ = [
    "REDACTED",
    "TRACE",
    "AppLogger",
    "BraceLogRecord",
    "EnrichFilter",
    "LoggingConfig",
    "RedactFilter",
    "RedactionPolicy",
    "redact",
]
