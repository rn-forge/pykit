"""Tests for rn_forge.auth.principal."""

from datetime import datetime, timezone

import pytest
from assertpy import assert_that

from rn_forge.auth import Principal, Requirement, principal_from_claims
from rn_forge.web import AuthenticationFailed

pytestmark = pytest.mark.unit


# --- Principal ------------------------------------------------------------


def test_subject_is_the_only_required_field():
    principal = Principal(subject="u1")
    assert_that(principal.issuer).is_none()
    assert_that(principal.scopes).is_empty()
    assert_that(principal.mechanism).is_equal_to("bearer")


def test_principal_round_trips_through_the_dataclass_mixin():
    principal = Principal(
        subject="u1",
        issuer="https://idp.example",
        scopes=frozenset({"read"}),
        roles=frozenset({"admin"}),
        tenant="t1",
        claims={"email": "u@example.com"},
        mechanism="bearer",
        external_subject="ext-1",
        permissions=frozenset({"orders.read"}),
        attributes={"org": "o1"},
        auth_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        amr=frozenset({"pwd"}),
    )
    restored = Principal.from_dict(principal.as_dict())
    assert_that(restored).is_equal_to(principal)


def test_scopes_and_roles_are_separate():
    principal = Principal(
        subject="u1", scopes=frozenset({"read"}), roles=frozenset({"admin"})
    )
    assert_that(principal.scopes).does_not_contain("admin")
    assert_that(principal.roles).does_not_contain("read")


# --- Requirement ----------------------------------------------------------


READER = Principal(
    subject="u1",
    scopes=frozenset({"read", "list"}),
    permissions=frozenset({"orders.read", "orders.list"}),
)


def test_an_empty_requirement_means_authenticated_not_denied():
    assert_that(Requirement().is_satisfied_by(Principal(subject="u1"))).is_true()


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        (Requirement(any_scope=frozenset({"read"})), True),
        (Requirement(any_scope=frozenset({"read", "write"})), True),
        (Requirement(any_scope=frozenset({"write"})), False),
        (Requirement(all_scopes=frozenset({"read", "list"})), True),
        (Requirement(all_scopes=frozenset({"read", "write"})), False),
        (Requirement(any_permission=frozenset({"orders.read", "x.y"})), True),
        (Requirement(any_permission=frozenset({"orders.update"})), False),
        (Requirement(all_permissions=frozenset({"orders.read", "orders.list"})), True),
        (Requirement(all_permissions=frozenset({"orders.read", "x.y"})), False),
    ],
)
def test_each_of_the_set_forms(requirement, expected):
    assert_that(requirement.is_satisfied_by(READER)).is_equal_to(expected)


def test_the_clauses_are_anded_together():
    both = Requirement(
        all_scopes=frozenset({"read"}), all_permissions=frozenset({"orders.update"})
    )
    assert_that(both.is_satisfied_by(READER)).is_false()


def test_scope_clauses_only_narrow_access():
    requirement = Requirement(
        all_permissions=frozenset({"orders.read"}), all_scopes=frozenset({"write"})
    )
    assert_that(requirement.is_satisfied_by(READER)).is_false()


def test_roles_do_not_satisfy_permission_clauses():
    admin = Principal(subject="u1", roles=frozenset({"orders.update"}))
    requirement = Requirement(all_permissions=frozenset({"orders.update"}))
    assert_that(requirement.is_satisfied_by(admin)).is_false()


# --- principal_from_claims ------------------------------------------------


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
    assert_that(principal.permissions).is_empty()
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
