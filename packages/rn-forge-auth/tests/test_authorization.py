"""Tests for rn_forge.auth.authorization."""

import pytest
from assertpy import assert_that

from rn_forge.auth import Authorizer, Principal, Requirement, ScopeAuthorizer
from rn_forge.web import PermissionDenied

pytestmark = pytest.mark.unit

READER = Principal(
    subject="u1",
    scopes=frozenset({"read", "list"}),
    permissions=frozenset({"orders.read"}),
    roles=frozenset({"staff"}),
)


def test_the_default_authorizer_satisfies_the_protocol():
    assert_that(isinstance(ScopeAuthorizer(), Authorizer)).is_true()


def test_authorize_permits_a_satisfied_requirement():
    ScopeAuthorizer().authorize(
        READER, requires=Requirement(all_scopes=frozenset({"read"}))
    )


def test_a_scope_miss_raises_permission_denied_not_authentication_failed():
    """The 401/403 boundary: the caller IS authenticated."""
    authorizer = ScopeAuthorizer()
    requirement = Requirement(all_scopes=frozenset({"write"}))
    assert_that(authorizer.authorize).raises(PermissionDenied).when_called_with(
        READER, requires=requirement
    )
    with pytest.raises(PermissionDenied):
        authorizer.authorize(READER, requires=requirement)


def test_the_authorizer_is_silent_when_no_log_is_injected():
    """A library that logs where the consumer did not ask is worse than one that does not."""
    authorizer = ScopeAuthorizer()
    requirement = Requirement(all_permissions=frozenset({"orders.update"}))
    with pytest.raises(PermissionDenied):
        authorizer.authorize(READER, requires=requirement)


def test_the_injected_log_receives_the_refusal():
    seen: list[tuple[str, dict]] = []
    authorizer = ScopeAuthorizer(log=lambda msg, ctx: seen.append((msg, dict(ctx))))
    requirement = Requirement(all_permissions=frozenset({"orders.update"}))
    with pytest.raises(PermissionDenied):
        authorizer.authorize(READER, requires=requirement)
    assert_that(seen).is_length(1)
    assert_that(seen[0][0]).is_equal_to("authorization.denied")
    assert_that(seen[0][1]["subject"]).is_equal_to("u1")
