"""The inbox consumer: dedupe, dispatch and record one inbound event."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from django.db import router, transaction
from django.utils import timezone
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.integration.messaging import HandlerRegistry
from rn_forge.commons.logging import AppLogger

from rn_forge.django.messaging.models import AbstractInboxMessage

__all__ = ["UnknownMessageType", "process_event"]

_LOGGER = AppLogger.get_logger(__name__)


class UnknownMessageType(AppException):
    """No handler is registered for the event's type."""


def process_event(
    event: Mapping[str, Any],
    registry: HandlerRegistry,
    inbox_model: type[AbstractInboxMessage],
    *,
    id_key: str = "id",
    type_key: str = "type",
    clock: Callable[[], datetime] = timezone.now,
) -> bool:
    """Handle *event* once, however many times it is delivered.

    Handler writes and the processed marker commit atomically. Failures are
    recorded on the inbox row and re-raised for broker retry or dead-lettering.

    Args:
        event: The received message. ``id_key``/``type_key`` name its id and
            type members (``id``/``type``, as in CloudEvents, by default).
        registry: Type → handler.
        inbox_model: The consuming app's concrete inbox model.
        clock: Supplies ``received_at``/``processed_at``.

    Returns:
        ``True`` when the handler ran, ``False`` for a duplicate delivery.

    Raises:
        UnknownMessageType: No handler is registered for the type.
    """
    message_id, message_type = str(event[id_key]), str(event[type_key])
    alias = router.db_for_write(inbox_model)
    manager = inbox_model._default_manager.db_manager(alias)
    manager.get_or_create(
        message_id=message_id,
        defaults={"message_type": message_type, "received_at": clock()},
    )

    failure: Exception
    with transaction.atomic(using=alias):
        row = manager.select_for_update().get(message_id=message_id)
        if row.processed_at is not None:
            _LOGGER.debug(
                "Inbox duplicate skipped: id={} type={}", message_id, message_type
            )
            return False
        row.attempts += 1
        handler = registry.handler_for(message_type)
        try:
            if handler is None:
                raise UnknownMessageType("No handler for message type {}", message_type)
            with transaction.atomic(using=alias):
                handler(event)
        except Exception as exc:  # noqa: BLE001 - recorded here, re-raised below
            row.error = f"{type(exc).__name__}: {exc}"
            row.save(update_fields=["attempts", "error"])
            failure = exc
        else:
            row.processed_at = clock()
            row.error = ""
            row.save(update_fields=["attempts", "error", "processed_at"])
            return True
    _LOGGER.warning(
        "Inbox handler failed: id={} type={} error={}",
        message_id,
        message_type,
        row.error,
    )
    raise failure
