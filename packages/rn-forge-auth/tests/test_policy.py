"""Tests for rn_forge.auth.policy."""

import pytest

from rn_forge.auth import Principal, ResourcePolicy

pytestmark = pytest.mark.unit


class OwnerPolicy:
    def allows(
        self, principal: Principal, action: str, resource: dict[str, str]
    ) -> bool:
        return resource["owner"] == principal.subject

    def scope(self, principal: Principal, action: str, query: list[str]) -> list[str]:
        return [*query, f"owner={principal.subject}"]


def test_a_concrete_policy_satisfies_the_protocol():
    policy: ResourcePolicy[dict[str, str], list[str]] = OwnerPolicy()
    assert isinstance(policy, ResourcePolicy)
    me = Principal(subject="u1")
    assert policy.allows(me, "read", {"owner": "u1"}) is True
    assert policy.scope(me, "read", []) == ["owner=u1"]
