"""OidcProvider against the fake IdP: the login flow end to end over loopback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("authlib")

from assertpy import assert_that  # noqa: E402
from rn_forge.auth import (  # noqa: E402
    ExternalIdentity,
    InMemoryTransactionStore,
    LoginFailed,
    LoginFlow,
)
from rn_forge.auth.oidc import OidcProvider, UpstreamTokens  # noqa: E402
from rn_forge.auth.testing import FakeOidcProvider  # noqa: E402

pytestmark = pytest.mark.unit

type Make = Callable[..., OidcProvider]
type Browser = Callable[[str], Any]


def _flow(provider: OidcProvider) -> LoginFlow[Any]:
    return LoginFlow(
        {provider.id: provider},
        InMemoryTransactionStore(),
        return_to_prefixes=["/app"],
    )


def _login(
    flow: LoginFlow[Any], browser: Browser, request_of: Any, provider: str = "acme"
) -> Any:
    start = flow.begin(provider, request_of(), return_to="/app/orders")
    assert start.redirect_url is not None
    return start.transaction.id, browser(start.redirect_url)


def _failure(
    flow: LoginFlow[Any], transaction_id: str, callback: Any, provider: str = "acme"
) -> LoginFailed:
    with pytest.raises(LoginFailed) as caught:
        flow.complete(provider, callback, transaction_id=transaction_id)
    return caught.value


@pytest.mark.parametrize("enabled", [True, False])
def test_the_id_token_is_kept_only_for_rp_initiated_logout(
    make_provider: Make, browser: Browser, request_of: Any, enabled: bool
) -> None:
    flow = _flow(make_provider(rp_initiated_logout=enabled))
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    if enabled:
        assert_that(identity.id_token).is_not_none()
    else:
        assert_that(identity.id_token).is_none()
    assert_that(repr(identity)).does_not_contain("id_token")


def test_a_login_returns_the_return_to(
    make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    completed = flow.complete("acme", callback, transaction_id=transaction_id)

    assert_that(completed.return_to).is_equal_to("/app/orders")


def test_a_login_returns_the_identity(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(identity.provider).is_equal_to("acme")
    assert_that(identity.issuer).is_equal_to(idp.issuer)
    assert_that(identity.subject).is_equal_to("u1")
    assert_that(identity.email).is_equal_to("u1@example.com")
    assert_that(identity.name).is_equal_to("User One")
    assert_that(identity.email_verified).is_false()
    assert_that(identity.session_ref).starts_with("sid-")
    assert_that(identity.auth_time).is_instance_of(datetime)
    assert_that(identity.attributes).is_empty()


def test_the_authorization_request_carries_state_nonce_and_pkce(
    idp: FakeOidcProvider, make_provider: Make, request_of: Any
) -> None:
    provider = make_provider(max_age=300)

    start = provider.begin(request_of(), return_to="/app")

    query = parse_qs(urlsplit(start.redirect_url or "").query)
    transaction = start.transaction
    assert_that(query["state"]).is_equal_to([transaction.state])
    assert_that(query["nonce"]).is_equal_to([transaction.nonce])
    assert_that(query["code_challenge_method"]).is_equal_to(["S256"])
    assert_that(query["max_age"]).is_equal_to(["300"])
    assert_that(query["scope"]).is_equal_to(["openid email profile"])
    assert_that(query).does_not_contain_key("code_verifier")
    assert_that(transaction.code_verifier).is_length(86)
    assert_that(transaction.provider).is_equal_to("acme")


def test_a_wrong_response_iss_fails(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.faults.response_iss = True
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    assert_that(_failure(flow, transaction_id, callback).code).is_equal_to(
        "login_failed"
    )
    assert_that(idp.fetches("/token")).is_zero()


def test_a_missing_response_iss_fails_when_discovery_advertises_it(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.faults.response_iss_missing = True
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    failure = _failure(flow, transaction_id, callback)

    assert_that(failure.code).is_equal_to("login_failed")
    assert_that(failure.reason).contains("iss")


def test_a_userinfo_sub_mismatch_fails(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.faults.userinfo_sub_mismatch = True
    flow = _flow(make_provider(userinfo="always"))
    transaction_id, callback = _login(flow, browser, request_of)

    failure = _failure(flow, transaction_id, callback)

    assert_that(failure.code).is_equal_to("login_failed")
    assert_that(failure.reason).contains("UserInfo")


def test_a_replayed_callback_fails(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)
    flow.complete("acme", callback, transaction_id=transaction_id)

    assert_that(_failure(flow, transaction_id, callback).code).is_equal_to(
        "login_failed"
    )


def test_a_callback_with_another_browsers_transaction_fails(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider())
    _, victim_callback = _login(flow, browser, request_of)
    attacker_transaction, _ = _login(flow, browser, request_of)

    failure = _failure(flow, attacker_transaction, victim_callback)

    assert_that(failure.code).is_equal_to("login_failed")
    assert_that(failure.reason).contains("state")


def test_an_id_token_older_than_max_age_fails(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.auth_age = 3600.0
    flow = _flow(make_provider(max_age=300))
    transaction_id, callback = _login(flow, browser, request_of)

    failure = _failure(flow, transaction_id, callback)

    assert_that(failure.code).is_equal_to("login_failed")
    assert_that(failure.reason).contains("max_age")


def test_a_recent_authentication_passes_max_age(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider(max_age=300))
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(identity.subject).is_equal_to("u1")


def test_access_denied_is_reported_as_such(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.deny_authorization = True
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    assert_that(_failure(flow, transaction_id, callback).code).is_equal_to(
        "access_denied"
    )


def test_another_provider_error_is_login_failed(
    idp: FakeOidcProvider, make_provider: Make, request_of: Any
) -> None:
    provider = make_provider()
    transaction = provider.begin(request_of(), return_to="/app").transaction

    request = request_of({"state": transaction.state, "error": "server_error"})

    with pytest.raises(LoginFailed) as caught:
        provider.complete(request, transaction)

    assert_that(caught.value.code).is_equal_to("login_failed")


def test_a_wrong_state_fails_before_any_back_channel_call(
    idp: FakeOidcProvider, make_provider: Make, request_of: Any
) -> None:
    provider = make_provider()
    transaction = provider.begin(request_of(), return_to="/app").transaction

    request = request_of({"state": "other", "code": "c", "iss": idp.issuer})

    with pytest.raises(LoginFailed):
        provider.complete(request, transaction)

    assert_that(idp.fetches("/token")).is_zero()


def test_a_failed_code_exchange_is_login_failed(
    idp: FakeOidcProvider, make_provider: Make, request_of: Any
) -> None:
    provider = make_provider()
    transaction = provider.begin(request_of(), return_to="/app").transaction

    request = request_of(
        {"state": transaction.state, "code": "bogus", "iss": idp.issuer}
    )

    with pytest.raises(LoginFailed) as caught:
        provider.complete(request, transaction)

    assert_that(caught.value.code).is_equal_to("login_failed")


def test_discovery_with_another_issuer_fails_the_login(
    idp: FakeOidcProvider, make_provider: Make, request_of: Any
) -> None:
    idp.faults.discovery_issuer = True
    flow = _flow(make_provider())

    request = request_of()
    with pytest.raises(LoginFailed):
        flow.begin("acme", request, return_to="/app")


def test_a_claim_mapper_replaces_the_default(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    seen: dict[str, Any] = {}

    def mapper(provider: str, claims: Any) -> ExternalIdentity:
        seen.update(claims)
        return ExternalIdentity(provider, claims["iss"], claims["sub"], name="mapped")

    flow = _flow(make_provider(claim_mapper=mapper))
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(identity.name).is_equal_to("mapped")
    assert_that(seen).contains_key("nonce", "email")


def test_the_default_mapper_maps_the_standard_claims(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    idp.user.update(
        email_verified=True,
        picture="https://img.example/u1.png",
        groups=["staff", "ops"],
        amr=["pwd", "mfa"],
        department="R&D",
    )
    flow = _flow(make_provider())
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(identity.email_verified).is_true()
    assert_that(identity.picture).is_equal_to("https://img.example/u1.png")
    assert_that(identity.groups).is_equal_to(frozenset({"staff", "ops"}))
    assert_that(identity.amr).is_equal_to(frozenset({"pwd", "mfa"}))
    assert_that(identity.attributes).is_equal_to({"department": "R&D"})
    assert_that(identity.auth_time).is_less_than(datetime.now(UTC))


def test_userinfo_is_skipped_when_never(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    flow = _flow(make_provider(userinfo="never"))
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(idp.fetches("/userinfo")).is_zero()
    assert_that(identity.email).is_none()


def test_tokens_reach_only_the_token_hook(
    idp: FakeOidcProvider, make_provider: Make, browser: Browser, request_of: Any
) -> None:
    received: list[tuple[ExternalIdentity, UpstreamTokens]] = []
    flow = _flow(make_provider(token_hook=lambda i, t: received.append((i, t))))
    transaction_id, callback = _login(flow, browser, request_of)

    identity = flow.complete("acme", callback, transaction_id=transaction_id).identity

    assert_that(received).is_length(1)
    hooked_identity, tokens = received[0]
    assert_that(hooked_identity).is_equal_to(identity)
    assert_that(tokens.access_token).is_not_empty()
    assert_that(tokens.id_token.count(".")).is_equal_to(2)
    assert_that(repr(tokens)).does_not_contain(tokens.access_token, tokens.id_token)
    assert_that(str(identity)).does_not_contain(tokens.access_token)


def test_no_flow_logs_a_token_code_or_verifier(
    idp: FakeOidcProvider,
    make_provider: Make,
    browser: Browser,
    request_of: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    secrets_seen: set[str] = {idp.client_secret or ""}
    captured: list[UpstreamTokens] = []
    provider = make_provider(
        token_hook=lambda _, t: captured.append(t), userinfo="always"
    )
    flow = _flow(provider)

    def run(**faults: bool) -> None:
        for name, value in faults.items():
            setattr(idp.faults, name, value)
        start = flow.begin("acme", request_of(), return_to="/app")
        assert start.redirect_url is not None
        callback = browser(start.redirect_url)
        secrets_seen.update(
            [callback.query.get("code", ""), start.transaction.code_verifier or ""]
        )
        try:
            flow.complete("acme", callback, transaction_id=start.transaction.id)
        except LoginFailed:
            pass
        for name in faults:
            setattr(idp.faults, name, False)

    run()
    run(response_iss=True)
    run(response_iss_missing=True)
    run(userinfo_sub_mismatch=True)
    run(wrong_nonce=True)
    idp.deny_authorization = True
    run()
    idp.deny_authorization = False
    for tokens in captured:
        secrets_seen.update([tokens.access_token, tokens.id_token])

    assert_that(captured).is_not_empty()
    assert_that(caplog.records).is_not_empty()
    secrets_seen.discard("")
    for secret in secrets_seen:
        assert_that(caplog.text).does_not_contain(secret)


class TestOAuth2Mode:
    def test_a_login_maps_the_user_endpoint(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        idp.user.update(id=4711, picture="https://img.example/p.png")
        provider = make_oauth2_provider(subject_field="id")
        flow = _flow(provider)
        transaction_id, callback = _login(flow, browser, request_of, "social")

        identity = flow.complete(
            "social", callback, transaction_id=transaction_id
        ).identity

        assert_that(provider.kind).is_equal_to("oauth2")
        assert_that(identity.provider).is_equal_to("social")
        assert_that(identity.issuer).is_equal_to("https://social.example")
        assert_that(identity.subject).is_equal_to("4711")
        assert_that(identity.email).is_equal_to("u1@example.com")
        assert_that(identity.name).is_equal_to("User One")
        assert_that(identity.picture).is_equal_to("https://img.example/p.png")
        assert_that(idp.fetches("/userinfo")).is_equal_to(1)

    def test_the_request_has_state_and_pkce_but_no_nonce(
        self, idp: FakeOidcProvider, make_oauth2_provider: Make, request_of: Any
    ) -> None:
        start = make_oauth2_provider().begin(request_of(), return_to="/app")

        query = parse_qs(urlsplit(start.redirect_url or "").query)
        assert_that(query).contains_key("state", "code_challenge")
        assert_that(query).does_not_contain_key("nonce", "scope")
        assert_that(query["code_challenge_method"]).is_equal_to(["S256"])
        assert_that(start.transaction.nonce).is_none()

    def test_the_default_subject_field_is_sub(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        flow = _flow(make_oauth2_provider())
        transaction_id, callback = _login(flow, browser, request_of, "social")

        identity = flow.complete(
            "social", callback, transaction_id=transaction_id
        ).identity

        assert_that(identity.subject).is_equal_to("u1")

    def test_a_failed_user_call_is_login_failed(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        idp.faults.userinfo_error = True
        flow = _flow(make_oauth2_provider())
        transaction_id, callback = _login(flow, browser, request_of, "social")

        failure = _failure(flow, transaction_id, callback, "social")

        assert_that(failure.code).is_equal_to("login_failed")

    def test_a_user_without_the_subject_field_fails(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        flow = _flow(make_oauth2_provider(subject_field="login"))
        transaction_id, callback = _login(flow, browser, request_of, "social")

        assert_that(
            _failure(flow, transaction_id, callback, "social").code
        ).is_equal_to("login_failed")

    def test_access_denied_is_reported_as_such(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        idp.deny_authorization = True
        flow = _flow(make_oauth2_provider())
        transaction_id, callback = _login(flow, browser, request_of, "social")

        assert_that(
            _failure(flow, transaction_id, callback, "social").code
        ).is_equal_to("access_denied")

    def test_the_response_iss_is_checked_only_when_configured(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        idp.faults.response_iss = True
        lenient = _flow(make_oauth2_provider())
        transaction_id, callback = _login(lenient, browser, request_of, "social")
        assert_that(
            lenient.complete(
                "social", callback, transaction_id=transaction_id
            ).identity.subject
        ).is_equal_to("u1")

        strict = _flow(make_oauth2_provider(response_issuer=idp.issuer))
        transaction_id, callback = _login(strict, browser, request_of, "social")
        assert_that(
            _failure(strict, transaction_id, callback, "social").code
        ).is_equal_to("login_failed")

    def test_the_token_hook_receives_the_access_token_only(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        received: list[UpstreamTokens] = []
        flow = _flow(make_oauth2_provider(token_hook=lambda _, t: received.append(t)))
        transaction_id, callback = _login(flow, browser, request_of, "social")

        flow.complete("social", callback, transaction_id=transaction_id)

        assert_that(received).is_length(1)
        assert_that(received[0].access_token).is_not_empty()
        assert_that(received[0].id_token).is_none()

    def test_a_replayed_callback_fails(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
    ) -> None:
        flow = _flow(make_oauth2_provider())
        transaction_id, callback = _login(flow, browser, request_of, "social")
        flow.complete("social", callback, transaction_id=transaction_id)

        assert_that(
            _failure(flow, transaction_id, callback, "social").code
        ).is_equal_to("login_failed")

    def test_no_flow_logs_a_token_code_or_verifier(
        self,
        idp: FakeOidcProvider,
        make_oauth2_provider: Make,
        browser: Browser,
        request_of: Any,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        seen: set[str] = {idp.client_secret or ""}
        captured: list[UpstreamTokens] = []
        flow = _flow(
            make_oauth2_provider(
                token_hook=lambda _, t: captured.append(t),
                response_issuer=idp.issuer,
            )
        )

        def run() -> None:
            start = flow.begin("social", request_of(), return_to="/app")
            assert start.redirect_url is not None
            callback = browser(start.redirect_url)
            seen.update(
                [callback.query.get("code", ""), start.transaction.code_verifier or ""]
            )
            try:
                flow.complete("social", callback, transaction_id=start.transaction.id)
            except LoginFailed:
                pass

        run()
        idp.faults.userinfo_error = True
        run()
        idp.faults.userinfo_error = False
        idp.faults.response_iss = True
        run()
        idp.faults.response_iss = False
        idp.deny_authorization = True
        run()
        seen.update(t.access_token for t in captured)

        assert_that(captured).is_not_empty()
        assert_that(caplog.records).is_not_empty()
        seen.discard("")
        for secret in seen:
            assert_that(caplog.text).does_not_contain(secret)
