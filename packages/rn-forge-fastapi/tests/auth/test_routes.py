"""The ``/auth`` router, driven through FastAPI's TestClient and an offline IdP."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rn_forge.auth import (
    AccountRejected,
    AuthorizationContext,
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    ExternalIdentity,
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    PasswordIdentityProvider,
)
from rn_forge.auth.oidc import BackchannelLogout, LogoutTokenVerifier, OidcProvider
from rn_forge.auth.testing import FakeOidcProvider
from rn_forge.fastapi import (
    SESSION_COOKIE,
    TRANSACTION_COOKIE,
    AuthRoutesConfig,
    auth_router,
)

pytestmark = pytest.mark.unit

BASE_URL = "https://testserver"
TYPE_BASE = "https://errors.example/"


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
        self.versions: dict[str, int] = {}

    def resolve(self, account_id: str) -> AuthorizationContext:
        return AuthorizationContext(
            active=account_id not in self.inactive,
            session_version=self.versions.get(account_id, 1),
            roles=frozenset({"staff"}),
            permissions=frozenset({"orders.read"}),
        )


class _State:
    def __init__(self, contexts: _Contexts) -> None:
        self.bumped: list[str] = []
        self._contexts = contexts

    def set_active(self, account_id: str, active: bool) -> None:
        raise NotImplementedError

    def bump_session_version(self, account_id: str) -> int:
        self.bumped.append(account_id)
        versions = self._contexts.versions
        versions[account_id] = versions.get(account_id, 1) + 1
        return len(self.bumped)


def _verify(username: str, password: str) -> str | None:
    return username if password == "correct" and username == "ada" else None


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url=BASE_URL, follow_redirects=False)


def _set_cookies(response: Any) -> dict[str, Any]:
    cookies: SimpleCookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return dict(cookies)


class _World:
    """The mounted application: a client plus the fakes behind it."""

    def __init__(
        self,
        app: FastAPI,
        idp: FakeOidcProvider,
        config: AuthRoutesConfig,
        contexts: _Contexts,
        state: _State,
    ) -> None:
        self.app = app
        self.client = _client(app)
        self.idp = idp
        self.config = config
        self.contexts = contexts
        self.state = state

    def approve(self, login_location: str) -> str:
        """Follow the IdP's authorization redirect and return the callback URL."""

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with pytest.raises(urllib.error.HTTPError) as redirect:
            opener.open(login_location)
        parts = urlsplit(redirect.value.headers["Location"])
        return f"{parts.path}?{parts.query}"

    def sign_in_with_idp(self, return_to: str = "/orders") -> Any:
        start = self.client.get("/auth/login/acme", params={"return_to": return_to})
        return self.client.get(self.approve(start.headers["location"]))

    def password_login(self, client: TestClient | None = None) -> Any:
        return (client or self.client).post(
            "/auth/login/password", json={"username": "ada", "password": "correct"}
        )


@pytest.fixture
def idp() -> Iterator[FakeOidcProvider]:
    with FakeOidcProvider(
        client_id="web",
        redirect_uris=[f"{BASE_URL}/auth/callback/acme"],
        user={"sub": "u1", "email": "u1@example.com", "name": "User One"},
    ) as fake:
        yield fake


@pytest.fixture
def mount(idp: FakeOidcProvider) -> Callable[..., _World]:
    def build(
        *,
        debug: bool = False,
        prefix: str = "/auth",
        rp_initiated_logout: bool = False,
        **overrides: Any,
    ) -> _World:
        acme = OidcProvider(
            id="acme",
            issuer=idp.issuer,
            client_id="web",
            client_secret="fake-secret",
            redirect_uri=f"{BASE_URL}/auth/callback/acme",
            rp_initiated_logout=rp_initiated_logout,
        )
        providers: dict[str, Any] = {
            "acme": acme,
            "password": PasswordIdentityProvider(_verify),
        }
        if debug:
            providers["development"] = DevelopmentIdentityProvider(
                [DevelopmentAccount("alice", name="Alice")], debug=True
            )
        accounts = _Accounts()
        contexts = _Contexts()
        replay = InMemoryReplayStore()
        state = _State(contexts)
        config = AuthRoutesConfig(
            providers=providers,
            accounts=accounts,
            contexts=contexts,
            account_state=state,
            return_to_prefixes=["/orders", "/home"],
            default_return_to="/home",
            provider_names={"acme": "Acme"},
            backchannel={
                "acme": BackchannelLogout(
                    LogoutTokenVerifier.from_issuer(
                        idp.issuer, client_id="web", replay_store=replay
                    ),
                    accounts,
                )
            },
            replay=replay,
            debug=debug,
            problem_type_base=TYPE_BASE,
            **overrides,
        )
        app = FastAPI()
        app.include_router(auth_router(config, prefix=prefix))
        return _World(app, idp, config, contexts, state)

    return build


class TestProviders:
    def test_lists_id_name_and_kind_without_development_outside_debug(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        # A development provider is configured but not served outside debug.
        providers = dict(world.config.providers)
        providers["development"] = DevelopmentIdentityProvider(
            [DevelopmentAccount("alice")], debug=True
        )
        app = FastAPI()
        app.include_router(
            auth_router(
                AuthRoutesConfig(
                    **{**world.config.__dict__, "providers": providers, "debug": False}
                )
            )
        )

        response = _client(app).get("/auth/providers")

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

        response = world.client.get("/auth/login/acme", params={"return_to": "/orders"})

        assert response.status_code == 302
        assert response.headers["location"].startswith(world.idp.authorization_endpoint)
        cookie = _set_cookies(response)[TRANSACTION_COOKIE]
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/"
        assert cookie["max-age"] == "600"
        assert cookie["domain"] == ""

    def test_the_transaction_lives_in_the_configured_store(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemoryTransactionStore()
        world = mount(transactions=store)
        response = world.client.get("/auth/login/acme", params={"return_to": "/orders"})

        transaction = store.consume(_set_cookies(response)[TRANSACTION_COOKIE].value)

        assert transaction is not None
        assert (transaction.provider, transaction.return_to) == ("acme", "/orders")

    def test_the_callback_starts_a_session_and_redirects_to_return_to(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.sign_in_with_idp("/orders")

        assert response.status_code == 302
        assert response.headers["location"] == "/orders"
        cookies = _set_cookies(response)
        assert SESSION_COOKIE in cookies
        assert cookies[TRANSACTION_COOKIE]["max-age"] == "0"
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
        response = mount().client.get(
            "/auth/login/acme", params={"return_to": return_to}
        )

        assert response.headers["location"] == "/auth/error?error=login_failed"
        assert TRANSACTION_COOKIE not in _set_cookies(response)

    def test_an_unknown_provider_is_404(self, mount: Callable[..., _World]) -> None:
        client = mount().client

        assert client.get("/auth/login/nope").status_code == 404
        assert client.get("/auth/callback/nope").status_code == 404

    def test_a_denied_authorization_is_access_denied(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.idp.deny_authorization = True

        response = world.sign_in_with_idp()

        assert response.headers["location"] == "/auth/error?error=access_denied"
        assert SESSION_COOKIE not in _set_cookies(response)

    def test_a_rejected_account_is_not_provisioned(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.idp.user = {"sub": "stranger"}

        response = world.sign_in_with_idp()

        assert (
            response.headers["location"] == "/auth/error?error=account_not_provisioned"
        )
        assert SESSION_COOKIE not in _set_cookies(response)

    def test_an_inactive_account_is_access_denied(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.contexts.inactive.add("acct-u1")

        response = world.sign_in_with_idp()

        assert response.headers["location"] == "/auth/error?error=access_denied"
        assert SESSION_COOKIE not in _set_cookies(response)

    def test_a_callback_without_the_cookie_is_login_failed(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])

        response = _client(world.app).get(callback)

        assert response.headers["location"] == "/auth/error?error=login_failed"

    def test_a_callback_works_once(self, mount: Callable[..., _World]) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])
        assert world.client.get(callback).headers["location"] == "/orders"

        replay = world.client.get(callback)

        assert replay.headers["location"] == "/auth/error?error=login_failed"

    def test_a_callback_with_two_transaction_cookies_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])
        real = _set_cookies(start)[TRANSACTION_COOKIE].value

        response = _client(world.app).get(
            callback,
            headers={
                "cookie": f"{TRANSACTION_COOKIE}=planted; {TRANSACTION_COOKIE}={real}"
            },
        )

        assert response.headers["location"] == "/auth/error?error=login_failed"
        assert world.idp.fetches("/token") == 0
        assert SESSION_COOKIE not in _set_cookies(response)

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
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])
        secrets = [
            value
            for key, value in parse_qsl(urlsplit(callback).query)
            if key in {"code", "state"}
        ]
        secrets += [
            _set_cookies(start)[TRANSACTION_COOKIE].value,
            *(
                value
                for key, value in parse_qsl(urlsplit(start.headers["location"]).query)
                if key in {"nonce", "code_challenge"}
            ),
        ]
        client = _client(world.app) if outcome == "no_cookie" else world.client
        responses = [client.get(callback)]
        if outcome == "replay":
            responses.append(client.get(callback))

        locations = [response.headers["location"] for response in responses]
        # The TestClient's own httpx logger records the callback URL the test
        # itself requests; it is not the application's log.
        logged = "\n".join(
            record.getMessage() for record in caplog.records if record.name != "httpx"
        )
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
        client = mount(debug=False).client

        assert client.get("/auth/login/development").status_code == 404
        assert (
            client.get(
                "/auth/login/development", params={"account": "alice"}
            ).status_code
            == 404
        )
        assert client.get("/auth/callback/development").status_code == 404

    def test_a_development_provider_is_not_served_when_debug_is_off(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        providers = {
            **world.config.providers,
            "development": DevelopmentIdentityProvider(
                [DevelopmentAccount("alice")], debug=True
            ),
        }
        app = FastAPI()
        app.include_router(
            auth_router(
                AuthRoutesConfig(**{**world.config.__dict__, "providers": providers})
            )
        )
        client = _client(app)

        assert client.get("/auth/login/development").status_code == 404
        assert (
            client.get(
                "/auth/login/development", params={"account": "alice"}
            ).status_code
            == 404
        )

    def test_it_lists_the_fixture_accounts(self, mount: Callable[..., _World]) -> None:
        response = mount(debug=True).client.get("/auth/login/development")

        assert response.status_code == 200
        assert "data-rn-forge-dev-accounts" in response.text
        assert 'data-account="alice"' in response.text

    def test_an_account_parameter_signs_in(self, mount: Callable[..., _World]) -> None:
        world = mount(debug=True)

        response = world.client.get(
            "/auth/login/development",
            params={"account": "alice", "return_to": "/orders"},
        )

        assert response.headers["location"] == "/orders"
        assert world.client.get("/auth/session").json()["subject"] == "acct-alice"

    def test_an_unknown_account_goes_to_the_error_route(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount(debug=True).client.get(
            "/auth/login/development", params={"account": "mallory"}
        )

        assert response.headers["location"] == "/auth/error?error=login_failed"


class TestPasswordLogin:
    def test_a_json_login_returns_the_session_body(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.password_login()

        assert response.status_code == 200
        assert response.json()["subject"] == "acct-ada"
        assert SESSION_COOKIE in _set_cookies(response)
        assert world.client.get("/auth/session").status_code == 200

    def test_a_form_login_works(self, mount: Callable[..., _World]) -> None:
        response = mount().client.post(
            "/auth/login/password", data={"username": "ada", "password": "correct"}
        )

        assert response.status_code == 200

    def test_failures_are_alike_and_carry_no_challenge(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount().client

        wrong = client.post(
            "/auth/login/password", json={"username": "ada", "password": "bad"}
        )
        unknown = client.post(
            "/auth/login/password", json={"username": "nobody", "password": "bad"}
        )
        garbage = client.post(
            "/auth/login/password",
            content="{",
            headers={"content-type": "application/json"},
        )

        assert {wrong.status_code, unknown.status_code, garbage.status_code} == {401}
        assert {**wrong.json(), "traceId": None} == {**unknown.json(), "traceId": None}
        assert wrong.headers["content-type"] == "application/problem+json"
        assert "www-authenticate" not in wrong.headers
        assert SESSION_COOKIE not in _set_cookies(wrong)

    def test_only_post_is_allowed(self, mount: Callable[..., _World]) -> None:
        assert mount().client.get("/auth/login/password").status_code == 405


class TestSessionAndLogout:
    def test_session_without_a_login_is_401_without_a_challenge(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.get("/auth/session")

        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert "www-authenticate" not in response.headers
        assert "no-store" in response.headers["cache-control"]

    def test_logout_ends_the_session(self, mount: Callable[..., _World]) -> None:
        world = mount()
        world.password_login()

        response = world.client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"redirect": None}
        assert _set_cookies(response)[SESSION_COOKIE]["max-age"] == "0"
        assert world.client.get("/auth/session").status_code == 401

    def test_logout_without_a_session_is_401(
        self, mount: Callable[..., _World]
    ) -> None:
        assert mount().client.post("/auth/logout").status_code == 401

    def test_logout_all_bumps_the_session_version_and_ends_the_session(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.password_login()

        response = world.client.post("/auth/logout/all")

        assert response.status_code == 200
        assert response.json() == {"redirect": None}
        assert world.state.bumped == ["acct-ada"]
        assert world.client.get("/auth/session").status_code == 401

    def test_unsafe_routes_reject_get(self, mount: Callable[..., _World]) -> None:
        client = mount().client

        assert client.get("/auth/logout").status_code == 405
        assert client.get("/auth/logout/all").status_code == 405

    def test_the_session_cookie_has_the_designs_flags(
        self, mount: Callable[..., _World]
    ) -> None:
        cookie = _set_cookies(mount().password_login())[SESSION_COOKIE]

        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/"
        assert cookie["domain"] == ""

    def test_the_session_holds_only_the_designs_content(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()

        session_id = world.client.cookies[SESSION_COOKIE]
        info = store.get(session_id)

        assert info is not None
        assert set(vars(info)) == {
            "account_id",
            "session_version",
            "provider",
            "issuer",
            "external_subject",
            "created_at",
            "expires_at",
            "auth_time",
            "amr",
            "session_ref",
            "id_token",
        }

    def test_login_gives_a_new_session_id_and_deletes_the_old_one(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()
        before = world.client.cookies[SESSION_COOKIE]

        world.password_login()

        after = world.client.cookies[SESSION_COOKIE]
        assert after != before
        assert store.get(before) is None
        assert store.get(after) is not None


class TestBackchannelLogout:
    def test_a_sid_token_revokes_the_sid(self, mount: Callable[..., _World]) -> None:
        world = mount()

        response = world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sid="sid-1")},
        )

        assert response.status_code == 200
        assert world.config.replay.is_sid_revoked(world.idp.issuer, "sid-1")
        assert world.state.bumped == []

    def test_a_sub_token_bumps_the_account_session_version(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        response = world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert response.status_code == 200
        assert world.state.bumped == ["acct-u1"]

    def test_a_bad_or_replayed_token_is_400(self, mount: Callable[..., _World]) -> None:
        world = mount()
        token = world.idp.logout_token(sid="sid-1")
        url = "/auth/backchannel-logout/acme"

        assert (
            world.client.post(url, data={"logout_token": "garbage"}).status_code == 400
        )
        assert world.client.post(url, data={"logout_token": token}).status_code == 200
        assert world.client.post(url, data={"logout_token": token}).status_code == 400

    def test_an_unconfigured_provider_is_404(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.post("/auth/backchannel-logout/other", data={})

        assert response.status_code == 404
