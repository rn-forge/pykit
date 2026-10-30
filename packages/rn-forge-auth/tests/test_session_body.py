"""Tests for rn_forge.auth.session_body."""

from datetime import datetime, timedelta, timezone
from typing import get_args

import pytest
from assertpy import assert_that

from rn_forge.auth import (
    CALLBACK_ERRORS,
    AuthorizationContext,
    CallbackError,
    SessionBody,
    SessionInfo,
)

pytestmark = pytest.mark.unit

UTC = timezone.utc


def _session(**overrides: object) -> SessionInfo:
    values: dict[str, object] = {
        "account_id": "acct_8f14e45f",
        "session_version": 3,
        "provider": "workspace",
        "issuer": "https://idp.example",
        "external_subject": "idp-sub-99",
        "created_at": datetime(2026, 9, 27, 9, 12, 44, tzinfo=UTC),
        "expires_at": datetime(2026, 9, 27, 17, 12, 44, 987, tzinfo=UTC),
    }
    values.update(overrides)
    return SessionInfo(**values)  # type: ignore[arg-type]


def test_full_body_matches_the_design_example():
    session = _session(
        auth_time=datetime(
            2026, 9, 27, 11, 12, 44, tzinfo=timezone(timedelta(hours=2))
        ),
        amr=frozenset({"pwd", "mfa"}),
    )
    context = AuthorizationContext(
        active=True,
        session_version=3,
        permissions=frozenset({"orders.update", "orders.list", "orders.read"}),
        roles=frozenset({"store-manager"}),
        attributes={"org_units": [{"type": "store", "id": "S-104"}]},
    )
    body = SessionBody.build(
        session,
        context,
        name="Ada Lovelace",
        email="ada@example.com",
        picture="https://example.com/ada.png",
    )
    assert_that(body.to_json()).is_equal_to(
        {
            "subject": "acct_8f14e45f",
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "picture": "https://example.com/ada.png",
            "provider": "workspace",
            "roles": ["store-manager"],
            "permissions": ["orders.list", "orders.read", "orders.update"],
            "attributes": {"orgUnits": [{"type": "store", "id": "S-104"}]},
            "authTime": "2026-09-27T09:12:44Z",
            "amr": ["mfa", "pwd"],
            "expiresAt": "2026-09-27T17:12:44Z",
        }
    )


def test_minimal_body_omits_absent_fields():
    body = SessionBody.build(
        _session(), AuthorizationContext(active=True, session_version=3)
    )
    assert_that(body.to_json()).is_equal_to(
        {
            "subject": "acct_8f14e45f",
            "provider": "workspace",
            "roles": [],
            "permissions": [],
            "expiresAt": "2026-09-27T17:12:44Z",
        }
    )


def test_subject_is_the_account_id_not_the_external_subject():
    body = SessionBody.build(
        _session(), AuthorizationContext(active=True, session_version=3)
    )
    assert_that(body.subject).is_equal_to("acct_8f14e45f")
    assert_that(body.to_json()["subject"]).is_not_equal_to("idp-sub-99")


def test_attribute_keys_are_camelized_at_every_depth():
    context = AuthorizationContext(
        active=True,
        session_version=3,
        attributes={"tenant_id": "t1", "_private": 1, "a": {"inner_key": [{"x_y": 1}]}},
    )
    attributes = SessionBody.build(_session(), context).to_json()["attributes"]
    assert_that(attributes).is_equal_to(
        {"tenantId": "t1", "_private": 1, "a": {"innerKey": [{"xY": 1}]}}
    )


def test_naive_datetime_is_read_as_utc():
    body = SessionBody(
        subject="a", provider="p", expires_at=datetime(2026, 1, 2, 3, 4, 5)
    )
    assert_that(body.to_json()["expiresAt"]).is_equal_to("2026-01-02T03:04:05Z")


def test_callback_errors_are_the_closed_list():
    assert_that(get_args(CallbackError)).is_equal_to(
        ("access_denied", "account_not_provisioned", "login_failed")
    )
    assert_that(CALLBACK_ERRORS).is_equal_to(set(get_args(CallbackError)))
