"""A Celery app factory and a retryable-task preset.

Requires the ``celery`` extra. Not imported by any facade, so
``import rn_forge.django`` works without Celery installed.

This is convenience, not extraction: it is the handful of lines every Django +
Celery project writes in ``celery.py``, plus the retry settings the outbox relay
task wants, so a project wiring :func:`rn_forge.django.messaging.make_outbox_relay`
does not re-derive them::

    # myproject/celery.py
    from rn_forge.django.celery import RETRYABLE_TASK_KWARGS, make_app

    app = make_app("myproject")

    @app.task(**RETRYABLE_TASK_KWARGS)
    def publish_outbox() -> int:
        return relay()

Deliberately absent: a ``make_outbox_relay_task`` wrapper. The relay is a plain
callable, and wrapping it is the two lines above.
"""

from __future__ import annotations

from typing import Any, Final

from celery import Celery

__all__ = ["RETRYABLE_TASK_KWARGS", "make_app"]

RETRYABLE_TASK_KWARGS: Final[dict[str, Any]] = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_kwargs": {"max_retries": 5},
}
"""Spread into ``@shared_task(**RETRYABLE_TASK_KWARGS)``: exponential backoff, five retries.

A plain dict rather than a decorator, and its exact shape is asserted by a
test — consumers spread it directly, so a silent change here changes their
retry behaviour.
"""


def make_app(
    name: str,
    *,
    config_source: str = "django.conf:settings",
    namespace: str = "CELERY",
    autodiscover: bool = True,
) -> Celery:
    """Return a Celery app configured from Django settings.

    Args:
        name: The app's main module name.
        config_source: What ``config_from_object`` reads.
        namespace: The settings prefix: ``CELERY_BROKER_URL`` → ``broker_url``.
        autodiscover: Look for ``tasks.py`` in every installed app.
    """
    app = Celery(name)
    app.config_from_object(config_source, namespace=namespace)  # pyright: ignore[reportUnknownMemberType]  # celery ships partial annotations
    if autodiscover:
        app.autodiscover_tasks()  # pyright: ignore[reportUnknownMemberType]  # celery ships partial annotations
    return app
