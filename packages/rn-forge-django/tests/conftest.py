"""Configure Django settings for the rn-forge-django test suite.

Test-only models
----------------

A test that needs a concrete model declares it in the test module itself::

    class Widget(BaseModel):
        class Meta(BaseModel.Meta):
            app_label = "rn_forge_django"

and creates its table from a module-scoped autouse fixture over
:func:`create_tables`::

    @pytest.fixture(scope="module", autouse=True)
    def _tables(create_tables):
        create_tables(Widget)

The database is sqlite in-memory. sqlite has no ``SELECT ... FOR UPDATE`` and
Django refuses ``skip_locked`` on it, so row-locking production paths are not
proven by this suite; the modules that rely on them say so.
"""

import os
from collections.abc import Callable
from urllib.parse import unquote, urlsplit

import django
import pytest
from django.conf import settings
from opentelemetry import trace
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    set_global_response_propagator,
)
from opentelemetry.sdk.trace import TracerProvider

DATABASE_URL_ENV = "RN_FORGE_DJANGO_TEST_DATABASE_URL"


def _database() -> dict[str, object]:
    """sqlite in-memory, or PostgreSQL from ``RN_FORGE_DJANGO_TEST_DATABASE_URL``.

    ``postgresql://user:password@host:port/name``. The ``postgres``-marked tests
    (row locking, real sequences) need it and skip without it; CI's
    ``django-postgres`` job sets it.
    """
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    parts = urlsplit(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts.path.lstrip("/"),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "localhost",
        "PORT": str(parts.port or 5432),
    }


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "postgres: needs a PostgreSQL test database")
    if not settings.configured:
        settings.configure(
            DATABASES={"default": _database()},
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rn_forge.django.auth",
                # Installed so the suite fails if the app package ever imports
                # its models at package import time.
                "rn_forge.django.messaging",
            ],
            ALLOWED_HOSTS=["localhost", "testserver"],
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            USE_TZ=False,
        )
        django.setup()


@pytest.fixture(autouse=True, scope="session")
def _otel_sdk() -> None:
    """Configure a `TracerProvider` and response propagator once per process.

    `set_tracer_provider` can only be called once per process; a second call
    logs a warning and is ignored. Under a root-level `uv run pytest`, every
    package's conftest calls this, and the first call wins — harmless, since
    they are identical. Tests must not rely on replacing the provider between
    runs.
    """
    trace.set_tracer_provider(TracerProvider())
    set_global_response_propagator(TraceResponsePropagator())


@pytest.fixture(autouse=True)
def _clear_cache():
    """pytest-randomly reorders tests, so no cached value may cross between them."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(scope="session")
def create_tables(django_db_setup, django_db_blocker) -> Callable[..., None]:
    """Return a function creating the tables of test-only models, idempotently."""
    from django.db import connection

    def create(*models: type) -> None:
        with django_db_blocker.unblock():
            existing = set(connection.introspection.table_names())
            with connection.schema_editor() as editor:
                for model in models:
                    if model._meta.db_table not in existing:
                        editor.create_model(model)

    return create
