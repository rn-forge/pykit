from __future__ import annotations

import logging
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from django.http import SimpleCookie
from django.test import Client, override_settings
from rn_forge.auth import (
    AccountRejected,
    AuthorizationContext,
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    ExternalIdentity,
    PasswordIdentityProvider,
)
from rn_forge.auth.oidc import BackchannelLogout, LogoutTokenVerifier, OidcProvider
from rn_forge.auth.testing import FakeOidcProvider
from rn_forge.django.auth import (
    TRANSACTION_COOKIE,
    AuthRoutesConfig,
    CacheReplayStore,
    CacheTransactionStore,
    auth_urlpatterns,
)

pytestmark = [pytest.mark.integration]

SESSION_COOKIE = "__Host-session"
CALLBACK = "/auth/callback/acme"


class _Accounts:
    def resolve(self, identity: ExternalIdentity) -> str:
        if identity.subject == "stranger":
            raise AccountRejected("not provisioned")
        return f"acct-{identity.subject}"

    def lookup(self, issuer: str, subject: str) -> str | None:
        return f"acct-{subject}"


class _Contexts:
    def __init__(self) -> None:
        self.inactive: set[str] = set()

    def resolve(self, account_id: str) -> AuthorizationContext:
        return AuthorizationContext(
            active=account_id not in self.inactive,
            session_version=1,
            roles=frozenset({"staff"}),
            permissions=frozenset({"orders.read"}),
        )


class _State:
    def __init__(self) -> None:
        self.bumped: list[str] = []

    def set_active(self, account_id: str, active: bool) -> None:
        raise NotImplementedError

    def bump_session_version(self, account_id: str) -> int:
        self.bumped.append(account_id)
        return len(self.bumped)


def _verify(username: str, password: str) -> str | None:
    return username if password == "correct" and username == "ada" else None


class _World:
    """The mounted application: a client plus the fakes behind it."""

    def __init__(self, client: Client, idp: FakeOidcProvider, config: AuthRoutesConfig):
        self.client = client
        self.idp = idp
        self.config = config
        self.contexts: _Contexts = config.contexts  # type: ignore[assignment]
        self.state: _State = config.account_state  # type: ignore[assignment]

    def approve(self, login_location: str) -> str:
        """Follow the IdP's authorization redirect and return the callback URL."""

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with pytest.raises(urllib.error.HTTPError) as redirect:
            opener.open(login_location)
        location = redirect.value.headers["Location"]
        parts = urlsplit(location)
        return f"{parts.path}?{parts.query}"

    def sign_in_with_idp(self, return_to: str = "/orders") -> Any:
        start = self.client.get("/auth/login/acme", {"return_to": return_to})
        return self.client.get(self.approve(start["Location"]))


@pytest.fixture
def idp() -> Iterator[FakeOidcProvider]:
    with FakeOidcProvider(
        client_id="web",
        redirect_uris=["http://testserver/auth/callback/acme"],
        user={"sub": "u1", "email": "u1@example.com", "name": "User One"},
    ) as fake:
        yield fake


@pytest.fixture
def mount(
    idp: FakeOidcProvider, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., _World]]:
    stack = ExitStack()

    def build(
        *,
        debug: bool = False,
        prefix: str = "auth",
        rp_initiated_logout: bool = False,
        **overrides: Any,
    ) -> _World:
        acme = OidcProvider(
            id="acme",
            issuer=idp.issuer,
            client_id="web",
            client_secret="fake-secret",
            redirect_uri="http://testserver/auth/callback/acme",
            rp_initiated_logout=rp_initiated_logout,
        )
        providers = {
            "acme": acme,
            "password": PasswordIdentityProvider(_verify),
            "development": DevelopmentIdentityProvider(
                [DevelopmentAccount("alice", name="Alice")], debug=True
            ),
        }
        accounts = _Accounts()
        config = AuthRoutesConfig(
            providers=providers,
            accounts=accounts,
            contexts=_Contexts(),
            account_state=_State(),
            return_to_prefixes=["/orders", "/home"],
            default_return_to="/home",
            provider_names={"acme": "Acme"},
            backchannel={
                "acme": BackchannelLogout(
                    LogoutTokenVerifier.from_issuer(
                        idp.issuer, client_id="web", replay_store=CacheReplayStore()
                    ),
                    accounts,
                )
            },
            **overrides,
        )
        module = ModuleType("test_routes_urlconf")
        module.urlpatterns = auth_urlpatterns(config, prefix=prefix)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module.__name__, module)
        stack.enter_context(
            override_settings(
                ROOT_URLCONF=module.__name__,
                DEBUG=debug,
                MIDDLEWARE=["django.contrib.sessions.middleware.SessionMiddleware"],
                SESSION_ENGINE="django.contrib.sessions.backends.cache",
                SESSION_COOKIE_NAME=SESSION_COOKIE,
            )
        )
        return _World(Client(), idp, config)

    yield build
    stack.close()


class TestProviders:
    def test_lists_id_name_and_kind_without_development_outside_debug(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.get("/auth/providers")

        assert response.status_code == 200
        assert response.json() == [
            {"id": "acme", "name": "Acme", "kind": "oidc"},
            {"id": "password", "name": "password", "kind": "password"},
        ]

    def test_lists_development_in_debug(self, mount: Callable[..., _World]) -> None:
        response = mount(debug=True).client.get("/auth/providers")

        assert [p["kind"] for p in response.json()] == [
            "oidc",
            "password",
            "development",
        ]

    def test_the_prefix_is_configurable(self, mount: Callable[..., _World]) -> None:
        client = mount(prefix="/api/identity/").client

        assert client.get("/api/identity/providers").status_code == 200
        assert client.get("/auth/providers").status_code == 404


class TestOidcLogin:
    def test_login_redirects_to_the_idp_with_a_transaction_cookie(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.client.get("/auth/login/acme", {"return_to": "/orders"})

        assert response.status_code == 302
        assert response["Location"].startswith(world.idp.authorization_endpoint)
        cookie = response.cookies[TRANSACTION_COOKIE]
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Lax"
        assert cookie["path"] == "/"
        assert cookie["max-age"] == 600
        assert cookie["domain"] == ""

    def test_the_transaction_lives_in_the_django_cache(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        response = world.client.get("/auth/login/acme", {"return_to": "/orders"})

        transaction = CacheTransactionStore().consume(
            response.cookies[TRANSACTION_COOKIE].value
        )

        assert transaction is not None
        assert (transaction.provider, transaction.return_to) == ("acme", "/orders")

    def test_the_callback_starts_a_session_and_redirects_to_return_to(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.sign_in_with_idp("/orders")

        assert response.status_code == 302
        assert response["Location"] == "/orders"
        assert SESSION_COOKIE in response.cookies
        assert response.cookies[TRANSACTION_COOKIE]["max-age"] == 0
        body = world.client.get("/auth/session").json()
        assert body["subject"] == "acct-u1"
        assert body["provider"] == "acme"
        assert body["roles"] == ["staff"]
        assert body["permissions"] == ["orders.read"]
        assert "expiresAt" in body

    @pytest.mark.parametrize(
        "return_to", ["https://evil.example/", "//evil.example", "/elsewhere"]
    )
    def test_a_bad_return_to_goes_to_the_error_route(
        self, mount: Callable[..., _World], return_to: str
    ) -> None:
        response = mount().client.get("/auth/login/acme", {"return_to": return_to})

        assert response["Location"] == "/auth/error?error=login_failed"
        assert TRANSACTION_COOKIE not in response.cookies

    def test_an_unknown_provider_is_404(self, mount: Callable[..., _World]) -> None:
        assert mount().client.get("/auth/login/nope").status_code == 404
        assert mount().client.get(f"/auth/callback/nope").status_code == 404

    def test_a_denied_authorization_is_access_denied(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.idp.deny_authorization = True

        response = world.sign_in_with_idp()

        assert response["Location"] == "/auth/error?error=access_denied"
        assert SESSION_COOKIE not in response.cookies

    def test_a_rejected_account_is_not_provisioned(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.idp.user = {"sub": "stranger"}

        response = world.sign_in_with_idp()

        assert response["Location"] == "/auth/error?error=account_not_provisioned"
        assert SESSION_COOKIE not in response.cookies

    def test_an_inactive_account_is_access_denied(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.contexts.inactive.add("acct-u1")

        response = world.sign_in_with_idp()

        assert response["Location"] == "/auth/error?error=access_denied"

    def test_a_callback_without_the_cookie_is_login_failed(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", {"return_to": "/orders"})
        callback = world.approve(start["Location"])

        response = Client().get(callback)

        assert response["Location"] == "/auth/error?error=login_failed"

    def test_a_callback_works_once(self, mount: Callable[..., _World]) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", {"return_to": "/orders"})
        callback = world.approve(start["Location"])
        assert world.client.get(callback)["Location"] == "/orders"

        replay = world.client.get(callback)

        assert replay["Location"] == "/auth/error?error=login_failed"

    def test_a_callback_with_two_transaction_cookies_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", {"return_to": "/orders"})
        callback = world.approve(start["Location"])
        real = start.cookies[TRANSACTION_COOKIE].value

        response = Client().get(
            callback,
            HTTP_COOKIE=f"{TRANSACTION_COOKIE}=planted; {TRANSACTION_COOKIE}={real}",
        )

        assert response["Location"] == "/auth/error?error=login_failed"
        assert world.idp.fetches("/token") == 0
        assert SESSION_COOKIE not in response.cookies

    @pytest.mark.parametrize("outcome", ["success", "replay", "denied", "no_cookie"])
    def test_no_secret_reaches_a_location_url_or_log_record(
        self,
        mount: Callable[..., _World],
        caplog: pytest.LogCaptureFixture,
        outcome: str,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        world = mount()
        world.idp.deny_authorization = outcome == "denied"
        start = world.client.get("/auth/login/acme", {"return_to": "/orders"})
        callback = world.approve(start["Location"])
        secrets = [
            value
            for key, value in parse_qsl(urlsplit(callback).query)
            if key in {"code", "state"}
        ]
        secrets += [
            start.cookies[TRANSACTION_COOKIE].value,
            *(
                value
                for key, value in parse_qsl(urlsplit(start["Location"]).query)
                if key in {"nonce", "code_challenge"}
            ),
        ]
        client = Client() if outcome == "no_cookie" else world.client
        responses = [client.get(callback)]
        if outcome == "replay":
            responses.append(client.get(callback))

        locations = [response["Location"] for response in responses]
        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert secrets
        for secret in secrets:
            assert all(secret not in location for location in locations)
            assert secret not in logged
        assert all(
            "error=" in location or location == "/orders" for location in locations
        )


class TestRpInitiatedLogout:
    def test_logout_returns_the_end_session_redirect_when_enabled(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(rp_initiated_logout=True)
        world.sign_in_with_idp()

        response = world.client.post("/auth/logout")

        redirect = response.json()["redirect"]
        assert redirect.startswith(world.idp.end_session_endpoint)
        query = dict(parse_qsl(urlsplit(redirect).query))
        assert query["post_logout_redirect_uri"] == "/"
        assert query["id_token_hint"]
        assert world.client.get("/auth/session").status_code == 401

    def test_logout_is_local_only_by_default(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()

        assert world.client.post("/auth/logout").json() == {"redirect": None}


class TestDevelopmentLogin:
    def test_it_exists_only_in_debug(self, mount: Callable[..., _World]) -> None:
        world = mount(debug=False)

        assert world.client.get("/auth/login/development").status_code == 404
        assert (
            world.client.get(
                "/auth/login/development", {"account": "alice"}
            ).status_code
            == 404
        )
        assert world.client.get("/auth/callback/development").status_code == 404

    def test_it_lists_the_fixture_accounts(self, mount: Callable[..., _World]) -> None:
        response = mount(debug=True).client.get("/auth/login/development")

        assert response.status_code == 200
        assert b"data-rn-forge-dev-accounts" in response.content
        assert b'data-account="alice"' in response.content

    def test_an_account_parameter_signs_in(self, mount: Callable[..., _World]) -> None:
        world = mount(debug=True)

        response = world.client.get(
            "/auth/login/development", {"account": "alice", "return_to": "/orders"}
        )

        assert response["Location"] == "/orders"
        assert world.client.get("/auth/session").json()["subject"] == "acct-alice"

    def test_an_unknown_account_goes_to_the_error_route(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount(debug=True).client.get(
            "/auth/login/development", {"account": "mallory"}
        )

        assert response["Location"] == "/auth/error?error=login_failed"


class TestPasswordLogin:
    def test_a_json_login_returns_the_session_body(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.client.post(
            "/auth/login/password",
            {"username": "ada", "password": "correct"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["subject"] == "acct-ada"
        assert SESSION_COOKIE in response.cookies
        assert world.client.get("/auth/session").status_code == 200

    def test_a_form_login_works(self, mount: Callable[..., _World]) -> None:
        response = mount().client.post(
            "/auth/login/password", {"username": "ada", "password": "correct"}
        )

        assert response.status_code == 200

    def test_failures_are_alike_and_carry_no_challenge(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount().client

        wrong = client.post(
            "/auth/login/password",
            {"username": "ada", "password": "bad"},
            content_type="application/json",
        )
        unknown = client.post(
            "/auth/login/password",
            {"username": "nobody", "password": "bad"},
            content_type="application/json",
        )
        garbage = client.post(
            "/auth/login/password", "{", content_type="application/json"
        )

        assert {wrong.status_code, unknown.status_code, garbage.status_code} == {401}
        assert wrong.json() == unknown.json()
        assert wrong["Content-Type"] == "application/problem+json"
        assert "WWW-Authenticate" not in wrong
        assert SESSION_COOKIE not in wrong.cookies

    def test_only_post_is_allowed(self, mount: Callable[..., _World]) -> None:
        assert mount().client.get("/auth/login/password").status_code == 405


class TestSessionAndLogout:
    def _sign_in(self, world: _World) -> None:
        world.client.post(
            "/auth/login/password",
            {"username": "ada", "password": "correct"},
            content_type="application/json",
        )

    def test_session_without_a_login_is_401_without_a_challenge(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.get("/auth/session")

        assert response.status_code == 401
        assert response["Content-Type"] == "application/problem+json"
        assert "WWW-Authenticate" not in response

    def test_logout_ends_the_session(self, mount: Callable[..., _World]) -> None:
        world = mount()
        self._sign_in(world)

        response = world.client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"redirect": None}
        assert world.client.get("/auth/session").status_code == 401

    def test_logout_without_a_session_is_401(
        self, mount: Callable[..., _World]
    ) -> None:
        assert mount().client.post("/auth/logout").status_code == 401

    def test_logout_all_bumps_the_session_version_and_ends_the_session(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        self._sign_in(world)

        response = world.client.post("/auth/logout/all")

        assert response.status_code == 200
        assert response.json() == {"redirect": None}
        assert world.state.bumped == ["acct-ada"]
        assert world.client.get("/auth/session").status_code == 401

    def test_unsafe_routes_reject_get(self, mount: Callable[..., _World]) -> None:
        client = mount().client

        assert client.get("/auth/logout").status_code == 405
        assert client.get("/auth/logout/all").status_code == 405


class TestBackchannelLogout:
    def test_a_sid_token_revokes_the_sid(self, mount: Callable[..., _World]) -> None:
        world = mount()

        response = world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sid="sid-1")},
        )

        assert response.status_code == 200
        assert CacheReplayStore().is_sid_revoked(world.idp.issuer, "sid-1")
        assert world.state.bumped == []

    def test_a_sub_token_bumps_the_account_session_version(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert response.status_code == 200
        assert world.state.bumped == ["acct-u1"]

    def test_a_bad_or_replayed_token_is_400(self, mount: Callable[..., _World]) -> None:
        world = mount()
        token = world.idp.logout_token(sid="sid-1")
        url = "/auth/backchannel-logout/acme"

        assert world.client.post(url, {"logout_token": "garbage"}).status_code == 400
        assert world.client.post(url, {"logout_token": token}).status_code == 200
        assert world.client.post(url, {"logout_token": token}).status_code == 400

    def test_an_unconfigured_provider_is_404(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.post("/auth/backchannel-logout/other", {})

        assert response.status_code == 404
