"""Concrete test-only outbox and inbox models, shared by the messaging tests."""

from rn_forge.django.messaging.models import AbstractInboxMessage, AbstractOutboxMessage


class OutboxMessage(AbstractOutboxMessage):
    class Meta(AbstractOutboxMessage.Meta):
        app_label = "rn_forge_django"


class InboxMessage(AbstractInboxMessage):
    class Meta(AbstractInboxMessage.Meta):
        app_label = "rn_forge_django"


class Ledger(AbstractInboxMessage):
    """Any table a handler writes to; reuses the inbox shape for brevity."""

    class Meta(AbstractInboxMessage.Meta):
        app_label = "rn_forge_django"
