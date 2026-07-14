import django
import pytest

pytestmark = pytest.mark.unit


def test_django_dependency() -> None:
    assert django.VERSION >= (4, 2)
