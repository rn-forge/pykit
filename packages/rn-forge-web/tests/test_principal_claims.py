"""Tests for rn_forge.web.auth.principal_from_claims."""

import pytest
from assertpy import assert_that

from rn_forge.web import AuthenticationFailed, principal_from_claims

pytestmark = pytest.mark.unit


def test_entra_shaped_claims():
    claims = {
        "sub": "u1",
        "iss": "https://login.microsoftonline.com/t/v2.0",
        "scp": "orders.read orders.write",
        "roles": ["Reader", "Approver"],
        "tid": "t",
    }
    principal = principal_from_claims(claims)
    assert_that(principal.subject).is_equal_to("u1")
    assert_that(principal.issuer).is_equal_to(claims["iss"])
    assert_that(principal.scopes).is_equal_to(
        frozenset({"orders.read", "orders.write"})
    )
    assert_that(principal.roles).is_equal_to(frozenset({"Reader", "Approver"}))
    assert_that(principal.tenant).is_equal_to("t")
    assert_that(dict(principal.claims)).is_equal_to(claims)
    assert_that(principal.mechanism).is_equal_to("bearer")


def test_rfc8693_scope_string_and_list_scp_are_merged():
    principal = principal_from_claims({"sub": "u1", "scope": "a b", "scp": ["c"]})
    assert_that(principal.scopes).is_equal_to(frozenset({"a", "b", "c"}))


def test_absent_optional_claims_default_to_empty():
    principal = principal_from_claims({"sub": "u1"}, mechanism="basic")
    assert_that(principal.scopes).is_empty()
    assert_that(principal.roles).is_empty()
    assert_that(principal.issuer).is_none()
    assert_that(principal.tenant).is_none()
    assert_that(principal.mechanism).is_equal_to("basic")


@pytest.mark.parametrize("claims", [{}, {"sub": ""}, {"sub": 7}])
def test_missing_subject_is_authentication_failed(claims):
    with pytest.raises(AuthenticationFailed):
        principal_from_claims(claims)
