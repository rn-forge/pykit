"""Tests for rn_forge.auth.accounts."""

import pytest

from rn_forge.auth import AccountRejected, AccountResolver, ExternalIdentity

pytestmark = pytest.mark.unit


class FakeResolver:
    def resolve(self, identity: ExternalIdentity) -> str:
        if identity.subject == "bad":
            raise AccountRejected("not provisioned")
        return "acct-1"

    def lookup(self, issuer: str, subject: str) -> str | None:
        return None


def test_a_concrete_resolver_satisfies_the_protocol():
    resolver = FakeResolver()
    assert isinstance(resolver, AccountResolver)
    assert (
        resolver.resolve(ExternalIdentity(provider="p", issuer="i", subject="s"))
        == "acct-1"
    )


def test_account_rejected_carries_a_reason():
    resolver = FakeResolver()
    identity = ExternalIdentity(provider="p", issuer="i", subject="bad")

    with pytest.raises(AccountRejected) as info:
        resolver.resolve(identity)
    assert info.value.reason == "not provisioned"


def test_a_reason_with_braces_is_kept_verbatim():
    assert AccountRejected("a {b}").reason == "a {b}"
