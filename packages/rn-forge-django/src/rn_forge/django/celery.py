"""Celery app factory and retryable-task defaults."""

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
