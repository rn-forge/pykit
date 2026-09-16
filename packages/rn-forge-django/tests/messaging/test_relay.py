from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone

from rn_forge.commons.integration.messaging import InMemoryMessageBus
from rn_forge.django.messaging.models import AbstractOutboxMessage
from rn_forge.django.messaging.relay import make_outbox_relay


class OutboxMessage(AbstractOutboxMessage):
    class Meta(AbstractOutboxMessage.Meta):
        app_label = "rn_forge_django"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(OutboxMessage)


def _envelope(row):
    return {"id": str(row.message_id), "type": row.message_type, "data": row.payload}


def _rows(count, *, destination="orders"):
    base = timezone.now() - timedelta(minutes=10)
    return [
        OutboxMessage.objects.create(
            message_type="order.created",
            destination=destination,
            payload={"n": i},
            occurred_at=base + timedelta(seconds=i),
        )
        for i in range(count)
    ]


@pytest.mark.integration
@pytest.mark.django_db
class TestRelay:
    def test_empty_outbox_is_a_noop(self) -> None:
        bus = InMemoryMessageBus()
        assert make_outbox_relay(OutboxMessage, bus, envelope_builder=_envelope)() == 0
        assert bus.published == []

    def test_batch_size_is_honoured_oldest_first(self) -> None:
        rows = _rows(5)
        bus = InMemoryMessageBus()
        relay = make_outbox_relay(
            OutboxMessage, bus, envelope_builder=_envelope, batch_size=2
        )
        assert relay() == 2
        assert [event["data"]["n"] for _, event in bus.published] == [0, 1]
        assert OutboxMessage.objects.filter(published_at__isnull=True).count() == 3
        assert {
            r.pk for r in OutboxMessage.objects.filter(published_at__isnull=False)
        } == {
            rows[0].pk,
            rows[1].pk,
        }

    def test_drain_loop_publishes_everything_once(self) -> None:
        _rows(5)
        bus = InMemoryMessageBus()
        relay = make_outbox_relay(
            OutboxMessage, bus, envelope_builder=_envelope, batch_size=2
        )
        while relay():
            pass
        assert len(bus.published) == 5
        assert not OutboxMessage.objects.filter(published_at__isnull=True).exists()

    def test_envelope_builder_invoked_per_row_and_destination_used(self) -> None:
        _rows(2, destination="billing")
        calls = []
        bus = InMemoryMessageBus()

        def builder(row):
            calls.append(row.pk)
            return _envelope(row)

        make_outbox_relay(OutboxMessage, bus, envelope_builder=builder)()
        assert len(calls) == 2
        assert {destination for destination, _ in bus.published} == {"billing"}

    def test_publish_failure_leaves_the_batch_unpublished(self) -> None:
        _rows(3)

        class FlakyBus(InMemoryMessageBus):
            def publish(self, destination, event):
                if len(self.published) == 1:
                    raise ConnectionError("broker down")
                super().publish(destination, event)

        with pytest.raises(ConnectionError):
            make_outbox_relay(OutboxMessage, FlakyBus(), envelope_builder=_envelope)()
        assert OutboxMessage.objects.filter(published_at__isnull=True).count() == 3

    def test_lag_and_log_hooks(self) -> None:
        _rows(1)
        lags, events = [], []
        make_outbox_relay(
            OutboxMessage,
            InMemoryMessageBus(),
            envelope_builder=_envelope,
            on_lag_observed=lags.append,
            log=lambda event, context: events.append((event, dict(context))),
        )()
        assert len(lags) == 1 and lags[0] >= 600
        assert events[0][0] == "outbox.relay"
        assert events[0][1]["published"] == 1


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
class TestRelayLockingOnPostgres:
    """The relay's correctness is skip_locked; only PostgreSQL can show it."""

    @pytest.fixture(autouse=True)
    def _require_postgres(self):
        if connection.vendor != "postgresql":
            pytest.skip(
                "row locking needs PostgreSQL (set RN_FORGE_DJANGO_TEST_DATABASE_URL)"
            )

    def test_concurrent_relays_claim_disjoint_rows(self) -> None:
        _rows(4)
        locked, release = threading.Event(), threading.Event()

        def hold_first_two():
            try:
                with transaction.atomic():
                    list(
                        OutboxMessage.objects.select_for_update()
                        .filter(published_at__isnull=True)
                        .order_by("occurred_at")[:2]
                    )
                    locked.set()
                    release.wait(timeout=10)
            finally:
                connection.close()

        holder = threading.Thread(target=hold_first_two)
        holder.start()
        assert locked.wait(timeout=10)
        bus = InMemoryMessageBus()
        try:
            published = make_outbox_relay(
                OutboxMessage, bus, envelope_builder=_envelope
            )()
        finally:
            release.set()
            holder.join()
        assert published == 2
        assert [event["data"]["n"] for _, event in bus.published] == [2, 3]
