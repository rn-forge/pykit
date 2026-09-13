"""The outbox relay: claim, publish and mark one batch."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from django.db import router, transaction
from django.utils import timezone
from rn_forge.commons.integration.messaging import MessageBus
from rn_forge.commons.logging import AppLogger

from rn_forge.django.messaging.models import AbstractOutboxMessage

__all__ = ["make_outbox_relay"]

_LOGGER = AppLogger.get_logger(__name__)

type Log = Callable[[str, Mapping[str, Any]], None]


def _default_log(event: str, context: Mapping[str, Any]) -> None:
    _LOGGER.info("{} {}", event, " ".join(f"{k}={v}" for k, v in context.items()))


def make_outbox_relay[M: AbstractOutboxMessage](
    outbox_model: type[M],
    bus: MessageBus,
    *,
    envelope_builder: Callable[[M], Mapping[str, Any]],
    batch_size: int = 100,
    on_lag_observed: Callable[[float], None] | None = None,
    log: Log | None = None,
    clock: Callable[[], datetime] = timezone.now,
) -> Callable[[], int]:
    """Build a callable that claims, publishes and marks one batch of outbox rows.

    The returned callable takes no arguments and returns how many messages it
    published, so a caller drains the outbox with
    ``while relay(): pass`` — and a Celery beat task is one line around it::

        relay = make_outbox_relay(OutboxMessage, bus, envelope_builder=to_envelope)

        @shared_task
        def publish_outbox() -> int:
            return relay()

    Rows are claimed with ``select_for_update(skip_locked=True)`` in
    ``transaction.atomic()``, oldest ``occurred_at`` first, and every row is
    published to its own ``destination`` before the batch is marked. A publish
    error rolls the claim back, so the batch is retried whole — at-least-once;
    see the package docstring.

    Args:
        outbox_model: The consuming app's concrete outbox model.
        bus: Where messages go.
        envelope_builder: Row → the event mapping published. Called once per row.
        batch_size: The most rows claimed per call.
        on_lag_observed: Called once per non-empty batch with the age, in
            seconds, of its oldest row — wire it to your metrics backend.
        log: Receives ``outbox.relay`` per non-empty batch. Defaults to
            ``AppLogger`` at info.
        clock: Supplies ``published_at`` and the lag reference.
    """
    emit: Log = log if log is not None else _default_log

    def relay() -> int:
        alias = router.db_for_write(outbox_model)
        manager = outbox_model._default_manager.db_manager(alias)
        with transaction.atomic(using=alias):
            batch = list(
                manager.select_for_update(skip_locked=True)
                .filter(published_at__isnull=True)
                .order_by("occurred_at", "pk")[:batch_size]
            )
            if not batch:
                return 0
            for row in batch:
                bus.publish(row.destination, envelope_builder(row))
            now = clock()
            manager.filter(pk__in=[row.pk for row in batch]).update(published_at=now)
        lag = max((now - batch[0].occurred_at).total_seconds(), 0.0)
        if on_lag_observed is not None:
            on_lag_observed(lag)
        emit("outbox.relay", {"published": len(batch), "lag_seconds": round(lag, 3)})
        return len(batch)

    return relay
