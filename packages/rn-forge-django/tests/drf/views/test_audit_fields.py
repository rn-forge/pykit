from __future__ import annotations

import pytest

pytest.importorskip("rest_framework")

from rn_forge.django.drf.views import AuditFieldsViewMixin  # noqa: E402

pytestmark = pytest.mark.unit


class _User:
    is_authenticated = True
    is_staff = False

    def __init__(self, email: str) -> None:
        self.email = email


class _AuditFieldsView(AuditFieldsViewMixin):
    def __init__(self, user: _User) -> None:
        self.request = type("Request", (), {"user": user})()


def test_prepares_create_audit_fields() -> None:
    prepared = _AuditFieldsView(_User("auditor@example.com")).prepare_create_data({})

    assert prepared == {
        "created_by": "auditor@example.com",
        "updated_by": "auditor@example.com",
    }


def test_prepares_update_audit_fields() -> None:
    prepared = _AuditFieldsView(_User("auditor@example.com")).prepare_update_data(
        {"created_by": "original@example.com"}
    )

    assert prepared == {"updated_by": "auditor@example.com"}
