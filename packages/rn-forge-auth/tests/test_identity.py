"""Tests for rn_forge.auth.identity."""

import dataclasses
from datetime import UTC, datetime
from typing import get_args

import pytest

import rn_forge.auth as auth
from rn_forge.auth import (
    ExternalIdentity,
    IdentityProvider,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Request:
    pass


class FakeProvider:
    id = "fake"
    kind: ProviderKind = "development"

    def begin(self, request: Request, *, return_to: str) -> LoginStart:
        tx = LoginTransaction(
            id="t", provider=self.id, return_to=return_to, created_at=NOW
        )
        return LoginStart(transaction=tx, redirect_url=None)

    def complete(
        self, request: Request, transaction: LoginTransaction
    ) -> ExternalIdentity:
        return ExternalIdentity(provider=self.id, issuer="local", subject="u")

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        return None


def test_provider_kind_is_closed():
    assert set(get_args(ProviderKind)) == {"oidc", "oauth2", "password", "development"}


def test_external_identity_defaults():
    identity = ExternalIdentity(provider="p", issuer="i", subject="s")
    assert identity.email is None
    assert identity.email_verified is False
    assert identity.groups == frozenset()
    assert identity.amr == frozenset()
    assert identity.attributes == {}
    assert (
        identity.attributes
        is not ExternalIdentity(provider="p", issuer="i", subject="s").attributes
    )


def test_login_transaction_defaults():
    tx = LoginTransaction(id="t", provider="p", return_to="/", created_at=NOW)
    assert (tx.state, tx.nonce, tx.code_verifier) == (None, None, None)
    assert tx.extra == {}


def test_session_info_defaults():
    info = SessionInfo(
        account_id="a",
        session_version=1,
        provider="p",
        issuer="i",
        external_subject="s",
        created_at=NOW,
        expires_at=NOW,
    )
    assert info.auth_time is None
    assert info.amr == frozenset()
    assert info.session_ref is None
    assert info.id_token is None


@pytest.mark.parametrize(
    "instance",
    [
        ExternalIdentity(provider="p", issuer="i", subject="s"),
        LoginTransaction(id="t", provider="p", return_to="/", created_at=NOW),
        LoginStart(
            transaction=LoginTransaction(
                id="t", provider="p", return_to="/", created_at=NOW
            ),
            redirect_url="https://idp",
        ),
    ],
)
def test_values_are_frozen(instance: object):
    field = dataclasses.fields(instance)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field, "x")


def test_session_info_is_frozen():
    info = SessionInfo("a", 1, "p", "i", "s", NOW, NOW)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.account_id = "b"  # type: ignore[misc]


def test_a_concrete_provider_satisfies_the_protocol():
    provider: IdentityProvider[Request] = FakeProvider()
    assert isinstance(provider, IdentityProvider)
    start = provider.begin(Request(), return_to="/home")
    assert start.redirect_url is None
    assert start.transaction.return_to == "/home"


def test_every_contract_is_exported():
    for name in (
        "AccountRejected",
        "AccountResolver",
        "AuthorizationContext",
        "AuthorizationContextProvider",
        "ResourcePolicy",
    ):
        assert hasattr(auth, name)
