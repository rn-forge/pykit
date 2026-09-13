from __future__ import annotations

import pytest

celery = pytest.importorskip("celery")

from django.test import override_settings  # noqa: E402

from rn_forge.django.celery import RETRYABLE_TASK_KWARGS, make_app  # noqa: E402

pytestmark = pytest.mark.unit


def test_make_app_reads_the_namespaced_django_settings() -> None:
    with override_settings(
        CELERY_BROKER_URL="memory://", CELERY_TASK_ALWAYS_EAGER=True
    ):
        app = make_app("orders", autodiscover=False)
        assert isinstance(app, celery.Celery)
        assert app.main == "orders"
        assert app.conf.broker_url == "memory://"
        assert app.conf.task_always_eager is True


def test_custom_namespace() -> None:
    with override_settings(JOBS_BROKER_URL="memory://jobs"):
        app = make_app("orders", namespace="JOBS", autodiscover=False)
        assert app.conf.broker_url == "memory://jobs"


def test_autodiscover_flag_is_respected(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        celery.Celery, "autodiscover_tasks", lambda self, *a, **k: calls.append(1)
    )
    make_app("orders", autodiscover=False)
    assert calls == []
    make_app("orders")
    assert calls == [1]


def test_retryable_task_kwargs_shape_is_stable() -> None:
    assert RETRYABLE_TASK_KWARGS == {
        "autoretry_for": (Exception,),
        "retry_backoff": True,
        "retry_kwargs": {"max_retries": 5},
    }


def test_retryable_kwargs_build_a_task() -> None:
    with override_settings(
        CELERY_TASK_ALWAYS_EAGER=True, CELERY_BROKER_URL="memory://"
    ):
        app = make_app("orders", autodiscover=False)

        @app.task(**RETRYABLE_TASK_KWARGS)
        def add(x, y):
            return x + y

        # autoretry reads retry_kwargs; task.max_retries itself is Celery's default.
        assert add.autoretry_for == (Exception,)
        assert add.retry_kwargs == {"max_retries": 5}
        assert add.retry_backoff is True
        assert add.delay(2, 3).get() == 5
