# Messaging: outbox and inbox

`rn_forge.django.messaging` makes publishing an event as reliable as the database change that
caused it, and makes handling a redelivered event a no-op.

## 1. Declare the tables

Add `"rn_forge.django.messaging"` to `INSTALLED_APPS`. The models are abstract; your app owns the
concrete tables and their migrations:

```python
from rn_forge.django.messaging.models import AbstractInboxMessage, AbstractOutboxMessage


class OutboxMessage(AbstractOutboxMessage):
    pass


class InboxMessage(AbstractInboxMessage):
    pass
```

## 2. Write to the outbox in the same transaction as the change

```python
from django.db import transaction


with transaction.atomic():
    order = Order.objects.create(...)
    OutboxMessage.objects.create(
        message_type="order.created",
        destination="orders",
        payload={"orderId": order.pk},
    )
```

Either both commit or neither does.

## 3. Relay committed rows to the bus

The bus is any `rn_forge.commons.integration.messaging.MessageBus` — an Azure Service Bus adapter
in production, `InMemoryMessageBus` in tests. The envelope is yours to define:

```python
from rn_forge.django.celery import RETRYABLE_TASK_KWARGS, make_app
from rn_forge.django.messaging.relay import make_outbox_relay

app = make_app("orders")


def to_envelope(row: OutboxMessage) -> dict:
    return {
        "specversion": "1.0",
        "id": str(row.message_id),
        "type": row.message_type,
        "source": "/orders",
        "time": row.occurred_at.isoformat(),
        "data": row.payload,
    }


relay = make_outbox_relay(
    OutboxMessage,
    bus,
    envelope_builder=to_envelope,
    on_lag_observed=outbox_lag_histogram.record,
)


@app.task(**RETRYABLE_TASK_KWARGS)
def publish_outbox() -> int:
    return relay()
```

Schedule `publish_outbox` with Celery beat (or call `relay()` from a management command loop).
Each call publishes at most `batch_size` rows and returns how many; `while relay(): pass` drains.

## 4. Handle inbound events exactly once

```python
from rn_forge.commons.integration.messaging import HandlerRegistry
from rn_forge.django.messaging.consumer import process_event

registry = HandlerRegistry().register("payment.captured", mark_order_paid)


def on_message(event):  # called by your broker consumer
    process_event(event, registry, InboxMessage)
```

A redelivered event returns `False` without running the handler. A handler's database writes and
the "processed" mark commit together. A failing handler has its error recorded on the inbox row and
is **re-raised**, so the broker can retry or dead-letter it.

## Guarantees and their limits

- **Out: at-least-once.** A publish error rolls the whole batch back, so rows already sent in that
  batch are sent again. Subscribers must dedupe — which is what the inbox is for.
- **Concurrent relays need PostgreSQL.** Rows are claimed with
  `select_for_update(skip_locked=True)`, so two relays take disjoint batches. sqlite has no row
  locks: run a single relay there. The locking behaviour is tested by the `postgres`-marked tests,
  which run when `RN_FORGE_DJANGO_TEST_DATABASE_URL` points at a PostgreSQL database.
- **No broker adapters here.** Azure Service Bus and friends implement the commons `MessageBus`
  protocol in their own packages.
