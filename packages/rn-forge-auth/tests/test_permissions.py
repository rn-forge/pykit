"""Tests for rn_forge.auth.permissions."""

import pytest
from assertpy import assert_that

from rn_forge.auth import (
    DEFAULT_PERMISSION_ACTION_MAP,
    AuthorizationContext,
    Principal,
    effective_permissions,
    requirement_for,
)

pytestmark = pytest.mark.unit

SCOPE_MAP = {
    "orders:read": frozenset({"orders.list", "orders.read"}),
    "orders:write": frozenset({"orders.create", "orders.update"}),
}
ADMIN = AuthorizationContext(
    active=True,
    session_version=1,
    permissions=frozenset({"orders.list", "orders.read", "orders.update"}),
    roles=frozenset({"administrator"}),
)


def _bearer(scopes: set[str]) -> Principal:
    scope_set = frozenset(scopes)
    return Principal(
        subject="a1",
        scopes=scope_set,
        permissions=effective_permissions(
            ADMIN.permissions,
            mechanism="bearer",
            scopes=scope_set,
            scope_map=SCOPE_MAP,
        ),
        roles=ADMIN.roles,
    )


# --- requirement_for ------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("partial_update", "orders.update"),
        ("retrieve", "orders.read"),
        ("destroy", "orders.delete"),
        ("export", "orders.export"),
    ],
)
def test_requirement_for_maps_the_action(action, expected):
    requirement = requirement_for("orders", action)
    assert_that(requirement.all_permissions).is_equal_to(frozenset({expected}))
    assert_that(requirement.any_permission).is_empty()


def test_an_explicit_action_map_merges_over_the_default():
    action_map = {"retrieve": "view", "export": "download"}
    assert_that(
        requirement_for("o", "retrieve", action_map=action_map).all_permissions
    ).is_equal_to(frozenset({"o.view"}))
    assert_that(
        requirement_for("o", "export", action_map=action_map).all_permissions
    ).is_equal_to(frozenset({"o.download"}))
    assert_that(
        requirement_for("o", "list", action_map=action_map).all_permissions
    ).is_equal_to(frozenset({"o.list"}))
    assert_that(DEFAULT_PERMISSION_ACTION_MAP["retrieve"]).is_equal_to("read")


# --- effective_permissions ------------------------------------------------


def test_a_read_only_token_cannot_exercise_an_administrators_write_permission():
    principal = _bearer({"orders:read"})
    assert_that(principal.permissions).is_equal_to(
        frozenset({"orders.list", "orders.read"})
    )
    assert_that(principal.roles).contains("administrator")
    assert_that(
        requirement_for("orders", "partial_update").is_satisfied_by(principal)
    ).is_false()
    assert_that(
        requirement_for("orders", "retrieve").is_satisfied_by(principal)
    ).is_true()


def test_a_write_scope_allows_what_the_account_holds():
    principal = _bearer({"orders:write"})
    assert_that(principal.permissions).is_equal_to(frozenset({"orders.update"}))
    assert_that(
        requirement_for("orders", "partial_update").is_satisfied_by(principal)
    ).is_true()


def test_a_scope_never_grants_a_permission_the_account_lacks():
    principal = _bearer({"orders:write"})
    assert_that(principal.permissions).does_not_contain("orders.create")


def test_an_unmapped_scope_allows_nothing():
    assert_that(_bearer({"unknown"}).permissions).is_empty()
    assert_that(_bearer(set()).permissions).is_empty()


def test_scopes_union():
    principal = _bearer({"orders:read", "orders:write", "unknown"})
    assert_that(principal.permissions).is_equal_to(ADMIN.permissions)


@pytest.mark.parametrize("mechanism", ["session", "basic"])
def test_session_and_basic_keep_the_account_permissions(mechanism):
    permissions = effective_permissions(
        ADMIN.permissions, mechanism=mechanism, scopes=frozenset(), scope_map=SCOPE_MAP
    )
    assert_that(permissions).is_equal_to(ADMIN.permissions)


def test_a_session_principal_has_no_scopes_and_the_account_permissions():
    principal = Principal(
        subject="a1", mechanism="session", permissions=ADMIN.permissions
    )
    assert_that(principal.scopes).is_empty()
    assert_that(
        requirement_for("orders", "partial_update").is_satisfied_by(principal)
    ).is_true()
