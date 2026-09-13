"""Transactional outbox and inbox messaging over the Django ORM.

Publishing an event and committing the database change that caused it cannot be
made atomic across a broker and a database. The outbox makes them atomic within
the database: the application writes an outbox row in the same transaction as
its change, and :func:`make_outbox_relay` publishes committed rows afterwards.
The inbox is the receiving half: :func:`process_event` records every message id
it handles, so a redelivered message is recognised and not handled twice.

- :class:`AbstractOutboxMessage` / :class:`AbstractInboxMessage` — abstract
  models; the consuming app declares the concrete tables and owns their
  migrations, as with ``BaseModel``.
- :func:`make_outbox_relay` — a factory returning a plain callable that claims,
  publishes and marks one batch. Wrap it in your own Celery task, management
  command or loop; this package takes no scheduler dependency.
- :func:`process_event` — dedupe, dispatch and record one inbound event.

The bus and the handler registry are ``rn_forge.commons.integration.messaging``'s
(``MessageBus``, ``HandlerRegistry``); this package defines neither.

Delivery semantics
------------------

**At-least-once out, effectively-once in.** The relay publishes inside the
claiming transaction and marks rows only after the whole batch published, so a
crash or a publish error mid-batch republishes the rows already sent. The inbox
is what absorbs those duplicates: a handler's writes and the row marking the
message processed commit together.

**The relay's correctness is** ``select_for_update(skip_locked=True)`` **on
PostgreSQL.** Two relays running concurrently each claim a disjoint batch.
sqlite has no row locks, so under sqlite a second concurrent relay may publish
the same rows; run one relay there. The locking behaviour is exercised by the
PostgreSQL job (``tests/messaging``, marker ``postgres``).

No existing library does a transactional outbox/inbox over the Django ORM — the
search found broker clients and Celery result backends, neither of which is
this — so it is written here.

**Envelopes are the consumer's.** The relay takes an ``envelope_builder``; a
CloudEvents builder is deliberately not shipped (see the django plan, Phase 10
gate 3), since the envelope is a contract between the application and its
subscribers.

Import from the submodules — ``.models``, ``.relay``, ``.consumer``. This package
is a Django app, and Django imports an app package before its registry is ready,
so its ``__init__`` must not import models (the same reason
``rn_forge.django.auth`` exports only its ``AppConfig``).
"""

from rn_forge.django.messaging.apps import MessagingConfig

__all__ = ["MessagingConfig"]
