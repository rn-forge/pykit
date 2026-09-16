from __future__ import annotations

import pytest

from rn_forge.commons.integration.messaging import HandlerRegistry
from rn_forge.django.messaging.consumer import UnknownMessageType, process_event
from rn_forge.django.messaging.models import AbstractInboxMessage


class InboxMessage(AbstractInboxMessage):
    class Meta(AbstractInboxMessage.Meta):
        app_label = "rn_forge_django"


class Ledger(AbstractInboxMessage):
    """Any table a handler writes to; reuses the inbox shape for brevity."""

    class Meta(AbstractInboxMessage.Meta):
        app_label = "rn_forge_django"


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(InboxMessage, Ledger)


def _event(message_id="m-1", message_type="order.created"):
    return {"id": message_id, "type": message_type, "data": {"order": 7}}


def _write_ledger(event):
    Ledger.objects.create(
        message_id=f"ledger-{event['id']}", message_type=event["type"]
    )


class TestProcessEvent:
    def test_first_delivery_runs_the_handler_and_records_it(self) -> None:
        registry = HandlerRegistry().register("order.created", _write_ledger)
        assert process_event(_event(), registry, InboxMessage) is True
        row = InboxMessage.objects.get(message_id="m-1")
        assert row.processed_at is not None
        assert (row.attempts, row.error) == (1, "")
        assert Ledger.objects.count() == 1

    def test_redelivery_is_deduplicated(self) -> None:
        calls = []
        registry = HandlerRegistry().register("order.created", calls.append)
        assert process_event(_event(), registry, InboxMessage) is True
        assert process_event(_event(), registry, InboxMessage) is False
        assert len(calls) == 1

    def test_unknown_type_is_recorded_and_raised(self) -> None:
        with pytest.raises(UnknownMessageType):
            process_event(_event(message_type="nope"), HandlerRegistry(), InboxMessage)
        row = InboxMessage.objects.get(message_id="m-1")
        assert row.processed_at is None
        assert "UnknownMessageType" in row.error

    def test_handler_failure_is_recorded_reraised_and_its_writes_rolled_back(
        self,
    ) -> None:
        def failing(event):
            _write_ledger(event)
            raise RuntimeError("downstream refused")

        registry = HandlerRegistry().register("order.created", failing)
        with pytest.raises(RuntimeError, match="downstream refused"):
            process_event(_event(), registry, InboxMessage)
        row = InboxMessage.objects.get(message_id="m-1")
        assert row.processed_at is None
        assert row.attempts == 1
        assert "downstream refused" in row.error
        assert Ledger.objects.count() == 0

    def test_retry_after_failure_succeeds_and_clears_the_error(self) -> None:
        outcomes = [RuntimeError("once"), None]

        def flaky(event):
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome

        registry = HandlerRegistry().register("order.created", flaky)
        with pytest.raises(RuntimeError):
            process_event(_event(), registry, InboxMessage)
        assert process_event(_event(), registry, InboxMessage) is True
        row = InboxMessage.objects.get(message_id="m-1")
        assert (row.attempts, row.error) == (2, "")

    def test_custom_id_and_type_keys(self) -> None:
        registry = HandlerRegistry().register("created", lambda event: None)
        event = {"messageId": "x-9", "kind": "created"}
        assert process_event(
            event, registry, InboxMessage, id_key="messageId", type_key="kind"
        )
        assert InboxMessage.objects.filter(
            message_id="x-9", message_type="created"
        ).exists()
