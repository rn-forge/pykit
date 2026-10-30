from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

import rn_forge.auth as auth
from rn_forge.auth import LoginFailed
from rn_forge.auth import (
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    DevelopmentModeRequired,
    LoginTransaction,
    PasswordIdentityProvider,
)


@dataclass
class FakeRequest:
    form: Mapping[str, str] = field(default_factory=dict[str, str])
    query: Mapping[str, str] = field(default_factory=dict[str, str])


@pytest.fixture
def make_request():
    return FakeRequest


@pytest.fixture
def transaction() -> LoginTransaction:
    provider = PasswordIdentityProvider(lambda u, p: None)
    return provider.begin(FakeRequest(), return_to="/").transaction


def verify(username: str, password: str) -> str | None:
    return "sub-1" if (username, password) == ("ann", "pw") else None


def test_password_begin_has_no_redirect() -> None:
    start = PasswordIdentityProvider(verify).begin(FakeRequest(), return_to="/x")
    assert start.redirect_url is None
    assert start.transaction.return_to == "/x"
    assert start.transaction.provider == "password"


def test_password_success(make_request, transaction) -> None:
    provider = PasswordIdentityProvider(verify)
    identity = provider.complete(
        make_request(form={"username": "ann", "password": "pw"}), transaction
    )
    assert (identity.issuer, identity.subject, identity.provider) == (
        "local",
        "sub-1",
        "password",
    )
    assert identity.amr == {"pwd"}
    assert provider.kind == "password"
    assert provider.logout_redirect(None, post_logout_redirect="/") is None  # type: ignore[arg-type]


def test_wrong_password_and_unknown_account_are_identical(
    make_request, transaction
) -> None:
    provider = PasswordIdentityProvider(verify)
    errors: list[LoginFailed] = []
    for form in (
        {"username": "ann", "password": "bad"},
        {"username": "nobody", "password": "pw"},
        {"username": "ann"},
    ):
        request = make_request(form=form)
        with pytest.raises(LoginFailed) as caught:
            provider.complete(request, transaction)
        errors.append(caught.value)
    assert {(type(e), e.code, e.reason) for e in errors} == {
        (
            LoginFailed,
            "login_failed",
            "invalid credentials",
        )
    }


ACCOUNTS = [
    DevelopmentAccount("alice", name="Alice <A>", email="a@example.com"),
    DevelopmentAccount('b"ob'),
]


def test_development_requires_debug() -> None:
    with pytest.raises(DevelopmentModeRequired):
        DevelopmentIdentityProvider(ACCOUNTS, debug=False)


def test_development_markup_is_stable_and_escaped() -> None:
    provider = DevelopmentIdentityProvider(ACCOUNTS, debug=True)
    assert provider.render_accounts(login_url="/login?x=1&y=2") == (
        "<ul data-rn-forge-dev-accounts>\n"
        '<li><a href="/login?x=1&amp;y=2&amp;account=alice" data-account="alice">'
        "Alice &lt;A&gt;</a></li>\n"
        '<li><a href="/login?x=1&amp;y=2&amp;account=b%22ob" '
        'data-account="b&quot;ob">b&quot;ob</a></li>\n'
        "</ul>"
    )


def test_development_markup_plain_login_url() -> None:
    provider = DevelopmentIdentityProvider([DevelopmentAccount("a")], debug=True)
    assert 'href="/login?account=a"' in provider.render_accounts(login_url="/login")


def test_development_account_parameter(make_request, transaction) -> None:
    provider = DevelopmentIdentityProvider(
        [DevelopmentAccount("alice", email="a@example.com", groups=frozenset({"g"}))],
        debug=True,
    )
    for request in (
        make_request(form={"account": "alice"}),
        make_request(query={"account": "alice"}),
    ):
        identity = provider.complete(request, transaction)
        assert (identity.issuer, identity.subject, identity.provider) == (
            "development",
            "alice",
            "development",
        )
        assert identity.email == "a@example.com"
        assert identity.groups == {"g"}


def test_development_unknown_account_fails(make_request, transaction) -> None:
    provider = DevelopmentIdentityProvider(ACCOUNTS, debug=True)
    for request in (make_request(), make_request(form={"account": "nobody"})):
        with pytest.raises(LoginFailed):
            provider.complete(request, transaction)


def test_facade_exports_local_names() -> None:
    for name in (
        "PasswordIdentityProvider",
        "PasswordVerifier",
        "DevelopmentIdentityProvider",
        "DevelopmentAccount",
        "DevelopmentModeRequired",
    ):
        assert name in auth.__all__
