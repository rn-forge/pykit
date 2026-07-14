"""Configure Django settings for the rn-forge-django test suite."""

import django
import pytest
from django.conf import settings


def pytest_configure(config: pytest.Config) -> None:
    if not settings.configured:
        settings.configure(
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rn_forge.django.auth",
            ],
            ALLOWED_HOSTS=["localhost", "testserver"],
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            USE_TZ=False,
        )
        django.setup()
