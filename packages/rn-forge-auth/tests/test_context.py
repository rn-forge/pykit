"""Tests for rn_forge.auth.context."""

import dataclasses

import pytest

from rn_forge.auth import AuthorizationContext, AuthorizationContextProvider

pytestmark = pytest.mark.unit


class FakeProvider:
    def resolve(self, account_id: str) -> AuthorizationContext:
        return AuthorizationContext(active=True, session_version=1)


def test_defaults_are_empty():
    ctx = AuthorizationContext(active=True, session_version=3)
    assert ctx.permissions == frozenset()
    assert ctx.roles == frozenset()
    assert ctx.attributes == {}


def test_context_is_frozen():
    ctx = AuthorizationContext(active=True, session_version=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.active = False  # type: ignore[misc]


def test_a_concrete_provider_satisfies_the_protocol():
    provider = FakeProvider()
    assert isinstance(provider, AuthorizationContextProvider)
    assert provider.resolve("a").active is True
