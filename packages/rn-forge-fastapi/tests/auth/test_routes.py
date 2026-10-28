"""The ``/auth`` router, driven through FastAPI's TestClient and an offline IdP."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from rn_forge.auth import (
    LoginTransaction,
    audit,
    SessionInfo,
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
    InMemoryCsrfStore,
    InMemoryRateLimiter,
    RateLimit,
    SessionMiddleware,
    active_session,
    auth_router,
    rotate_session,
    sessions_for,
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


class _Browser(TestClient):
    """A test client that sends ``Origin`` and copies the ``XSRF-TOKEN`` cookie into the header."""

    def request(self, method: str, url: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        if method.upper() not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Origin", BASE_URL)
            if not any(name.lower() == "x-xsrf-token" for name in headers):
                if not self.cookies.get("XSRF-TOKEN"):
                    super().request("GET", "/auth/session")
                token = self.cookies.get("XSRF-TOKEN")
                if token:
                    headers["X-XSRF-TOKEN"] = token
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def _client(app: FastAPI) -> TestClient:
    return _Browser(app, base_url=BASE_URL, follow_redirects=False)


def _bare_client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url=BASE_URL, follow_redirects=False)


def _set_cookies(response: Any) -> dict[str, Any]:
    cookies: SimpleCookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return dict(cookies)


class _SharedSessions:
    """Stands in for a store shared between processes: it wraps the in-memory one."""

    def __init__(self, inner: InMemorySessionStore) -> None:
        self.inner = inner

    def create(self, session: SessionInfo, *, idle_ttl: timedelta) -> str:
        return self.inner.create(session, idle_ttl=idle_ttl)

    def get(self, session_id: str) -> SessionInfo | None:
        return self.inner.get(session_id)

    def touch(self, session_id: str, *, idle_ttl: timedelta) -> bool:
        return self.inner.touch(session_id, idle_ttl=idle_ttl)

    def delete(self, session_id: str) -> None:
        self.inner.delete(session_id)

    def rotate(self, session_id: str, *, idle_ttl: timedelta) -> str | None:
        return self.inner.rotate(session_id, idle_ttl=idle_ttl)


class _SharedReplay:
    def __init__(self, inner: InMemoryReplayStore) -> None:
        self.inner = inner

    def record_once(self, key: str, *, ttl: timedelta) -> bool:
        return self.inner.record_once(key, ttl=ttl)

    def revoke_sid(self, issuer: str, sid: str, *, ttl: timedelta) -> None:
        self.inner.revoke_sid(issuer, sid, ttl=ttl)

    def is_sid_revoked(self, issuer: str, sid: str) -> bool:
        return self.inner.is_sid_revoked(issuer, sid)


class _SharedTransactions:
    def __init__(self, inner: InMemoryTransactionStore) -> None:
        self.inner = inner

    def save(self, transaction: LoginTransaction, *, ttl: timedelta) -> None:
        self.inner.save(transaction, ttl=ttl)

    def consume(self, transaction_id: str) -> LoginTransaction | None:
        return self.inner.consume(transaction_id)


class _SharedCsrf:
    def __init__(self, inner: InMemoryCsrfStore) -> None:
        self.inner = inner

    def save(self, key: str, token: str, *, ttl: timedelta) -> None:
        self.inner.save(key, token, ttl=ttl)

    def get(self, key: str) -> str | None:
        return self.inner.get(key)

    def delete(self, key: str) -> None:
        self.inner.delete(key)


class _SharedLimiter:
    def __init__(self, inner: InMemoryRateLimiter) -> None:
        self.inner = inner

    def hit(self, scope: str, subject: str, rate: RateLimit) -> int | None:
        return self.inner.hit(scope, subject, rate)


class _Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)

    def advance(self, **kwargs: float) -> None:
        self.moment += timedelta(**kwargs)

    def now(self) -> datetime:
        return self.moment


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
        clock: _Clock | None = None,
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
        accounts = overrides.pop("accounts", None) or _Accounts()
        contexts = _Contexts()
        now = clock.now if clock else None
        sessions = overrides.pop("sessions", None) or InMemorySessionStore(
            **({"clock": now} if now else {})
        )
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
            replay=_SharedReplay(replay),
            csrf=_SharedCsrf(InMemoryCsrfStore(**({"clock": now} if now else {}))),
            limiter=overrides.pop("limiter", None)
            or _SharedLimiter(InMemoryRateLimiter()),
            sessions=_SharedSessions(sessions),
            transactions=_SharedTransactions(
                overrides.pop("transactions", None) or InMemoryTransactionStore()
            ),
            debug=debug,
            problem_type_base=TYPE_BASE,
            **({"clock": now} if now else {}),
            **overrides,
        )
        app = FastAPI()
        app.add_middleware(SessionMiddleware, sessions=sessions_for(config))
        app.include_router(auth_router(config, prefix=prefix))

        @app.get("/touch")
        async def touch() -> dict[str, str]:
            return {}

        @app.post("/rotate")
        async def rotate(request: Request) -> dict[str, str]:
            await rotate_session(request)
            return {}

        @app.get("/guarded")
        async def guarded(request: Request) -> dict[str, str]:
            if active_session(request) is None:
                raise HTTPException(status_code=401)
            return {}

        @app.get("/whoami")
        async def whoami(request: Request) -> dict[str, str | None]:
            active = active_session(request)
            return {"account": active.info.account_id if active else None}

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
    @pytest.mark.security_control("return-to-relative")
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

    @pytest.mark.security_control("one-time-transactions")
    def test_a_callback_without_the_cookie_is_login_failed(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])

        response = _client(world.app).get(callback)

        assert response.headers["location"] == "/auth/error?error=login_failed"

    @pytest.mark.security_control("one-time-transactions")
    def test_a_callback_works_once(self, mount: Callable[..., _World]) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        callback = world.approve(start.headers["location"])
        assert world.client.get(callback).headers["location"] == "/orders"

        replay = world.client.get(callback)

        assert replay.headers["location"] == "/auth/error?error=login_failed"

    @pytest.mark.security_control("one-time-transactions")
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
    @pytest.mark.security_control("no-tokens-in-urls-or-logs")
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

    @pytest.mark.security_control("problem-responses")
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
    @pytest.mark.security_control("problem-responses")
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
        session_id = _session_id(world)

        response = world.client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"redirect": None}
        assert world.config.sessions.get(session_id) is None
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


def _session_id(world: _World) -> str:
    return world.client.cookies[SESSION_COOKIE]


def _sid(world: _World) -> str:
    info = world.config.sessions.get(_session_id(world))
    assert info is not None
    assert info.session_ref is not None
    return info.session_ref


def _other_browser(world: _World, session_id: str | None = None) -> TestClient:
    other = _client(world.app)
    other.cookies.set(
        SESSION_COOKIE, session_id or _session_id(world), domain="testserver.local"
    )
    return other


def _max_age(response: Any) -> int | None:
    cookie = _set_cookies(response).get(SESSION_COOKIE)
    return int(cookie["max-age"]) if cookie else None


class TestSessionMiddleware:
    def test_the_session_is_available_to_routes(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        assert world.client.get("/whoami").json() == {"account": None}

        world.password_login()

        assert world.client.get("/whoami").json() == {"account": "acct-ada"}

    def test_a_normal_request_refreshes_the_cookie_max_age(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.password_login()

        response = world.client.get("/touch")

        assert _max_age(response) == 1800
        cookie = _set_cookies(response)[SESSION_COOKIE]
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/"

    def test_get_session_leaves_the_cookie_alone(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.password_login()

        assert SESSION_COOKIE not in _set_cookies(world.client.get("/auth/session"))

    def test_a_cookie_naming_no_valid_session_is_cleared(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.client.cookies.set(SESSION_COOKIE, "stale", domain="testserver.local")

        response = world.client.get("/touch")

        assert _max_age(response) == 0

    def test_a_request_without_a_cookie_sets_none(
        self, mount: Callable[..., _World]
    ) -> None:
        assert SESSION_COOKIE not in _set_cookies(mount().client.get("/touch"))


@pytest.mark.security_control("session-lifecycle")
class TestTimeouts:
    def test_an_idle_session_expires_after_30_minutes(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        world.password_login()

        clock.advance(minutes=29)
        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=2)

        assert world.client.get("/auth/session").status_code == 401

    def test_a_normal_request_slides_the_idle_expiry(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        world.password_login()

        for _ in range(3):
            clock.advance(minutes=20)
            assert world.client.get("/touch").status_code == 200

        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=31)
        assert world.client.get("/auth/session").status_code == 401

    def test_get_session_does_not_extend_the_session(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        world.password_login()

        clock.advance(minutes=20)
        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=15)

        assert world.client.get("/auth/session").status_code == 401

    def test_the_absolute_timeout_ends_an_active_session(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        world.password_login()

        for _ in range(35):
            clock.advance(minutes=20)
            assert world.client.get("/touch").status_code == 200
        assert world.client.get("/auth/session").json()["expiresAt"] == (
            "2026-10-28T21:00:00Z"
        )
        # Twenty minutes remain; the cookie never outlives the session.
        assert _max_age(world.client.get("/touch")) == 1200
        clock.advance(minutes=21)

        assert world.client.get("/auth/session").status_code == 401

    def test_an_expired_session_is_deleted(self, mount: Callable[..., _World]) -> None:
        clock = _Clock()
        store = InMemorySessionStore(clock=clock.now)
        world = mount(clock=clock, sessions=store)
        world.password_login()
        session_id = _session_id(world)

        clock.advance(hours=13)
        assert world.client.get("/auth/session").status_code == 401

        assert store.get(session_id) is None

    def test_the_timeouts_are_configurable(self, mount: Callable[..., _World]) -> None:
        clock = _Clock()
        world = mount(clock=clock, idle_timeout=timedelta(minutes=5))
        world.password_login()

        clock.advance(minutes=6)

        assert world.client.get("/auth/session").status_code == 401


@pytest.mark.security_control("session-lifecycle")
class TestRotation:
    def test_login_gives_a_new_id_and_the_old_one_is_unreadable(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()
        before = _session_id(world)
        stale = _other_browser(world)

        world.password_login()

        assert _session_id(world) != before
        assert store.get(before) is None
        assert stale.get("/auth/session").status_code == 401

    def test_rotate_session_changes_the_id_and_keeps_the_login(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()
        before = _session_id(world)
        stale = _other_browser(world)

        response = world.client.post("/rotate")

        after = _session_id(world)
        assert response.status_code == 200
        assert after != before
        assert _max_age(response) == 1800
        assert store.get(before) is None
        assert store.get(after) is not None
        assert world.client.get("/auth/session").status_code == 200
        assert stale.get("/auth/session").status_code == 401

    def test_rotation_does_not_extend_the_absolute_timeout(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        world.password_login()
        expires = world.client.get("/auth/session").json()["expiresAt"]

        clock.advance(minutes=20)
        world.client.post("/rotate")

        assert world.client.get("/auth/session").json()["expiresAt"] == expires

    def test_rotating_without_a_session_changes_nothing(
        self, mount: Callable[..., _World]
    ) -> None:
        response = mount().client.post("/rotate")

        assert response.status_code == 200
        assert SESSION_COOKIE not in _set_cookies(response)


@pytest.mark.security_control("session-lifecycle")
class TestRevocation:
    def test_a_version_mismatch_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()
        session_id = _session_id(world)
        world.state.bump_session_version("acct-ada")

        response = world.client.get("/auth/session")

        assert response.status_code == 401
        assert store.get(session_id) is None

    def test_a_disabled_account_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.password_login()
        session_id = _session_id(world)
        world.contexts.inactive.add("acct-ada")

        assert world.client.get("/auth/session").status_code == 401
        assert store.get(session_id) is None

    def test_a_revoked_sid_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        store = InMemorySessionStore()
        world = mount(sessions=store)
        world.sign_in_with_idp()
        session_id = _session_id(world)
        assert world.client.get("/auth/session").status_code == 200

        world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sid=_sid(world))},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert store.get(session_id) is None

    def test_logout_ends_this_session_only(self, mount: Callable[..., _World]) -> None:
        world = mount()
        other = _client(world.app)
        world.password_login()
        world.password_login(other)

        world.client.post("/auth/logout")

        assert world.client.get("/auth/session").status_code == 401
        assert other.get("/auth/session").status_code == 200

    def test_logout_all_ends_every_session_of_the_account(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        other = _client(world.app)
        world.password_login()
        world.password_login(other)

        world.client.post("/auth/logout/all")

        assert other.get("/auth/session").status_code == 401

    def test_a_sid_backchannel_logout_ends_that_session_only(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        other = _client(world.app)
        world.password_login(other)

        world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sid=_sid(world))},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert other.get("/auth/session").status_code == 200

    def test_a_sub_backchannel_logout_ends_every_session_of_the_account(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        second = _client(world.app)
        start = second.get("/auth/login/acme", params={"return_to": "/orders"})
        second.get(world.approve(start.headers["location"]))

        world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert second.get("/auth/session").status_code == 401


WORKERS = 4
REQUESTS_PER_PHASE = 3


def _race(world: _World, revoke: Callable[[], None]) -> tuple[int, int]:
    """Hammer the session routes from threads while *revoke* runs.

    The workers alternate ``GET /auth/session`` with a guarded request that
    extends the session, so a request in flight at the revocation may write the session
    back. A request that began after *revoke* returned must not succeed, and a
    fresh request at the end must be refused. Returns the number of requests
    seen before and after the revocation.
    """
    session_id = _session_id(world)
    revoked = threading.Event()
    stop = threading.Event()
    barrier = threading.Barrier(WORKERS + 1)
    lock = threading.Lock()
    seen: list[tuple[bool, int]] = []

    def worker() -> None:
        client = _other_browser(world, session_id)
        barrier.wait()
        turn = 0
        while not stop.is_set():
            after = revoked.is_set()
            status = client.get("/guarded" if turn % 2 else "/auth/session").status_code
            with lock:
                seen.append((after, status))
            turn += 1

    def wait_for(phase_after: bool) -> None:
        while True:
            with lock:
                total = sum(1 for after, _ in seen if after is phase_after)
            if total >= WORKERS * REQUESTS_PER_PHASE:
                return
            threading.Event().wait(0.001)

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    barrier.wait()
    wait_for(False)
    revoke()
    revoked.set()
    wait_for(True)
    stop.set()
    for thread in threads:
        thread.join()
    assert [status for after, status in seen if after and status == 200] == []
    assert _other_browser(world, session_id).get("/auth/session").status_code == 401
    return (
        sum(1 for after, _ in seen if not after),
        sum(1 for after, _ in seen if after),
    )


@pytest.mark.security_control("session-lifecycle")
class TestRevocationRaces:
    def test_no_request_succeeds_after_a_logout(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.password_login()

        before, after = _race(world, lambda: world.client.post("/auth/logout"))

        assert before
        assert after

    def test_no_request_succeeds_after_a_backchannel_logout(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        token = world.idp.logout_token(sid=_sid(world))

        def revoke() -> None:
            response = _client(world.app).post(
                "/auth/backchannel-logout/acme", data={"logout_token": token}
            )
            assert response.status_code == 200

        before, after = _race(world, revoke)

        assert before
        assert after

    def test_no_request_succeeds_after_an_account_is_disabled(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.password_login()

        before, after = _race(world, lambda: world.contexts.inactive.add("acct-ada"))

        assert before
        assert after


class TestInMemoryStoresOutsideDebug:
    def _config(self, **overrides: Any) -> AuthRoutesConfig:
        contexts = _Contexts()
        return AuthRoutesConfig(
            providers={},
            accounts=_Accounts(),
            contexts=contexts,
            account_state=_State(contexts),
            **{
                "problem_type_base": TYPE_BASE,
                "sessions": _SharedSessions(InMemorySessionStore()),
                "transactions": _SharedTransactions(InMemoryTransactionStore()),
                "replay": _SharedReplay(InMemoryReplayStore()),
                "csrf": _SharedCsrf(InMemoryCsrfStore()),
                "limiter": _SharedLimiter(InMemoryRateLimiter()),
            }
            | overrides,
        )

    @pytest.mark.parametrize(
        ("store", "name", "label"),
        [
            (InMemorySessionStore, "sessions", "sessions"),
            (InMemoryTransactionStore, "transactions", "transactions"),
            (InMemoryReplayStore, "replay", "replay"),
            (InMemoryCsrfStore, "csrf", "CSRF"),
            (InMemoryRateLimiter, "limiter", "rate limiter"),
        ],
    )
    def test_the_router_refuses_an_in_memory_store(
        self, store: Callable[[], Any], name: str, label: str
    ) -> None:
        config = self._config(**{name: store()})

        with pytest.raises(RuntimeError, match=f"The {label} store"):
            auth_router(config)

    @pytest.mark.parametrize(
        ("store", "name", "label"),
        [
            (InMemorySessionStore, "sessions", "sessions"),
            (InMemoryReplayStore, "replay", "replay"),
            (InMemoryCsrfStore, "csrf", "CSRF"),
        ],
    )
    def test_the_middleware_sessions_refuse_an_in_memory_store(
        self, store: Callable[[], Any], name: str, label: str
    ) -> None:
        with pytest.raises(RuntimeError, match=f"The {label} store"):
            sessions_for(self._config(**{name: store()}))

    def test_mounting_without_a_problem_type_base_fails(self) -> None:
        with pytest.raises(ValueError, match="problem_type_base"):
            self._config(problem_type_base="")

    def test_stores_shared_between_processes_are_accepted(self) -> None:
        auth_router(self._config())
        sessions_for(self._config())

    def test_debug_accepts_in_memory_stores(self) -> None:
        config = self._config(
            sessions=InMemorySessionStore(),
            transactions=InMemoryTransactionStore(),
            replay=InMemoryReplayStore(),
            csrf=InMemoryCsrfStore(),
            limiter=InMemoryRateLimiter(),
            debug=True,
        )

        auth_router(config)
        sessions_for(config)


@pytest.mark.security_control("csrf-and-origin")
class TestCsrf:
    """The synchronizer token, driven by a client that does not add the header itself."""

    @staticmethod
    def _bare(world: _World) -> TestClient:
        client = _bare_client(world.app)
        world.client = client
        return client

    @staticmethod
    def _token(client: TestClient) -> str:
        """Fetch the CSRF cookie from ``/auth/session``, as the SPA does."""
        response = client.get("/auth/session")
        assert response.status_code == 401
        return client.cookies["XSRF-TOKEN"]

    @staticmethod
    def _login(client: TestClient, token: str | None, **headers: str) -> Any:
        extra = {"X-XSRF-TOKEN": token} if token else {}
        return client.post(
            "/auth/login/password",
            json={"username": "ada", "password": "correct"},
            headers={"Origin": BASE_URL, **extra, **headers},
        )

    def test_session_always_sets_a_script_readable_csrf_cookie(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        response = client.get("/auth/session")

        cookie = _set_cookies(response)["XSRF-TOKEN"]
        assert cookie.value
        assert cookie["httponly"] == ""
        assert cookie["secure"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/"

    def test_an_anonymous_session_holds_the_token_for_ten_minutes(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)

        response = client.get("/auth/session")

        session = _set_cookies(response)[SESSION_COOKIE]
        assert session.value.startswith("anon.")
        assert session["max-age"] == "600"
        assert session["httponly"] is True
        assert world.config.sessions.get(session.value) is None
        assert world.config.csrf.get(session.value) == client.cookies["XSRF-TOKEN"]

    def test_session_keeps_the_token_while_the_session_is_anonymous(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())
        token = self._token(client)

        assert self._token(client) == token

    def test_login_is_protected_before_sign_in(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())
        token = self._token(client)

        missing = self._login(client, None)
        wrong = self._login(client, "x" * 43)
        ok = self._login(client, token)

        assert (missing.status_code, wrong.status_code) == (403, 403)
        assert ok.status_code == 200

    def test_a_cookie_less_unsafe_request_to_an_app_route_is_not_checked(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        assert client.post("/rotate").status_code == 200

    def test_an_unsafe_request_with_a_session_cookie_and_no_token_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        stale = client.post("/rotate", cookies={SESSION_COOKIE: "unknown-id"})
        anonymous = client.post("/rotate", cookies={SESSION_COOKIE: "anon.unknown"})

        assert (stale.status_code, anonymous.status_code) == (403, 403)

    def test_password_login_with_no_cookie_and_no_token_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        response = client.post(
            "/auth/login/password",
            json={"username": "ada", "password": "correct"},
            headers={"Origin": BASE_URL},
        )

        assert response.status_code == 403

    def test_a_request_with_no_anonymous_session_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        response = self._login(client, "x" * 43)

        assert response.status_code == 403

    def test_an_expired_anonymous_session_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        clock = _Clock()
        world = mount(clock=clock)
        client = self._bare(world)
        token = self._token(client)
        clock.advance(minutes=11)

        response = self._login(client, token)

        assert response.status_code == 403
        # The SPA refetches the session, which starts a new anonymous one.
        client.get("/auth/session")
        assert self._login(client, client.cookies["XSRF-TOKEN"]).status_code == 200

    def test_a_rejection_is_the_csrf_failed_problem(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        response = self._login(client, None)

        body = response.json()
        assert response.status_code == 403
        assert response.headers["content-type"] == "application/problem+json"
        assert body["type"] == f"{TYPE_BASE}csrf-failed"
        assert body["detail"] == "CSRF verification failed."
        assert "www-authenticate" not in response.headers

    def test_login_replaces_the_session_and_the_token(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        token = self._token(client)
        anonymous = client.cookies[SESSION_COOKIE]

        response = self._login(client, token)

        cookies = _set_cookies(response)
        assert cookies["XSRF-TOKEN"].value != token
        assert cookies[SESSION_COOKIE].value != anonymous
        assert world.config.csrf.get(anonymous) is None
        assert world.config.csrf.get(cookies[SESSION_COOKIE].value) == (
            cookies["XSRF-TOKEN"].value
        )
        # The anonymous pair no longer protects anything.
        assert (
            client.post(
                "/auth/logout",
                headers={"Origin": BASE_URL, "X-XSRF-TOKEN": token},
            ).status_code
            == 403
        )

    def test_an_oidc_login_replaces_the_token(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        token = self._token(client)

        response = world.sign_in_with_idp()

        assert _set_cookies(response)["XSRF-TOKEN"].value != token
        assert client.get("/auth/session").status_code == 200

    def test_logout_needs_the_token_and_rotates_it(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        self._login(client, self._token(client))
        token = client.cookies["XSRF-TOKEN"]
        session_id = client.cookies[SESSION_COOKIE]
        origin = {"Origin": BASE_URL}

        assert client.post("/auth/logout", headers=origin).status_code == 403
        response = client.post(
            "/auth/logout", headers={**origin, "X-XSRF-TOKEN": token}
        )

        cookies = _set_cookies(response)
        assert response.status_code == 200
        assert cookies["XSRF-TOKEN"].value != token
        assert world.config.csrf.get(session_id) is None
        # The fresh anonymous session protects the next login.
        assert self._login(client, cookies["XSRF-TOKEN"].value).status_code == 200

    def test_logout_all_needs_the_token(self, mount: Callable[..., _World]) -> None:
        client = self._bare(mount())
        self._login(client, self._token(client))

        response = client.post("/auth/logout/all", headers={"Origin": BASE_URL})

        assert response.status_code == 403

    def test_session_mints_a_token_for_a_session_that_has_none(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        self._login(client, self._token(client))
        world.config.csrf.delete(client.cookies[SESSION_COOKIE])

        response = client.get("/auth/session")

        assert response.status_code == 200
        token = _set_cookies(response)["XSRF-TOKEN"].value
        assert world.config.csrf.get(client.cookies[SESSION_COOKIE]) == token

    def test_a_token_pair_from_another_browser_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        victim = self._bare(world)
        self._login(victim, self._token(victim))
        attacker = _bare_client(world.app)
        attacker_token = self._token(attacker)
        origin = {"Origin": BASE_URL}

        replayed = victim.post(
            "/auth/logout",
            headers={**origin, "X-XSRF-TOKEN": attacker_token},
            cookies={"XSRF-TOKEN": attacker_token},
        )

        assert replayed.status_code == 403
        assert replayed.json()["type"] == f"{TYPE_BASE}csrf-failed"
        assert victim.get("/auth/session").status_code == 200

    def test_the_apps_own_unsafe_routes_are_protected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())
        self._login(client, self._token(client))
        token = client.cookies["XSRF-TOKEN"]

        assert client.post("/rotate", headers={"Origin": BASE_URL}).status_code == 403
        ok = client.post("/rotate", headers={"Origin": BASE_URL, "X-XSRF-TOKEN": token})
        assert ok.status_code == 200

    def test_rotate_session_carries_the_token(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        self._login(client, self._token(client))
        token = client.cookies["XSRF-TOKEN"]
        old = client.cookies[SESSION_COOKIE]

        client.post("/rotate", headers={"Origin": BASE_URL, "X-XSRF-TOKEN": token})

        new = client.cookies[SESSION_COOKIE]
        assert new != old
        assert world.config.csrf.get(old) is None
        assert world.config.csrf.get(new) == token
        assert (
            client.post(
                "/rotate", headers={"Origin": BASE_URL, "X-XSRF-TOKEN": token}
            ).status_code
            == 200
        )

    def test_an_ended_session_deletes_its_token(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._bare(world)
        self._login(client, self._token(client))
        session_id = client.cookies[SESSION_COOKIE]
        world.contexts.inactive.add("acct-ada")

        assert client.get("/touch").status_code == 200
        assert world.config.sessions.get(session_id) is None
        assert world.config.csrf.get(session_id) is None

    def test_an_untrusted_origin_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())
        token = self._token(client)

        response = self._login(client, token, Origin="https://evil.example")

        assert response.status_code == 403

    def test_a_null_origin_is_rejected(self, mount: Callable[..., _World]) -> None:
        client = self._bare(mount())

        assert (
            self._login(client, self._token(client), Origin="null").status_code == 403
        )

    def test_a_trusted_origin_passes(self, mount: Callable[..., _World]) -> None:
        client = self._bare(mount(trusted_origins=["https://app.example"]))
        token = self._token(client)

        response = self._login(client, token, Origin="https://app.example")

        assert response.status_code == 200

    def test_a_missing_origin_needs_a_trusted_referer_over_https(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())
        token = self._token(client)
        body = {"username": "ada", "password": "correct"}
        headers = {"X-XSRF-TOKEN": token}

        none = client.post("/auth/login/password", json=body, headers=headers)
        evil = client.post(
            "/auth/login/password",
            json=body,
            headers={**headers, "Referer": "https://evil.example/page"},
        )
        own = client.post(
            "/auth/login/password",
            json=body,
            headers={**headers, "Referer": f"{BASE_URL}/page"},
        )

        assert (none.status_code, evil.status_code) == (403, 403)
        assert own.status_code == 200

    def test_cross_site_fetch_metadata_is_rejected_even_from_a_trusted_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount(trusted_origins=["https://app.example"]))
        token = self._token(client)

        cross = self._login(
            client,
            token,
            Origin="https://app.example",
            **{"Sec-Fetch-Site": "cross-site"},
        )
        same = self._login(client, token, **{"Sec-Fetch-Site": "same-origin"})

        assert cross.status_code == 403
        assert same.status_code == 200

    def _forwarded(self, client: TestClient, token: str) -> Any:
        return self._login(
            client,
            token,
            Origin="https://app.example",
            **{"X-Forwarded-Host": "app.example", "X-Forwarded-Proto": "https"},
        )

    def test_forged_forwarded_headers_do_not_vouch_for_an_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        assert self._forwarded(client, self._token(client)).status_code == 403

    def test_a_trusted_proxy_vouches_for_the_forwarded_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        trusted = self._behind_proxy(mount, "203.0.113.0/24")
        token = self._token(trusted)

        assert self._forwarded(trusted, token).status_code == 200

    def test_a_proxy_that_is_not_trusted_does_not_vouch(
        self, mount: Callable[..., _World]
    ) -> None:
        other = self._behind_proxy(mount, "198.51.100.0/24")

        assert self._forwarded(other, self._token(other)).status_code == 403

    @staticmethod
    def _behind_proxy(mount: Callable[..., _World], network: str) -> TestClient:
        world = mount(trusted_proxies=[network])
        return TestClient(
            world.app,
            base_url=BASE_URL,
            follow_redirects=False,
            client=("203.0.113.9", 4000),
        )

    def test_back_channel_logout_is_exempt(self, mount: Callable[..., _World]) -> None:
        world = mount()
        client = self._bare(world)

        response = client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sid="sid-x")},
        )

        assert response.status_code == 200

    def test_a_request_with_a_bearer_authorization_header_is_exempt(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._bare(mount())

        cookies = {SESSION_COOKIE: "unknown-id"}
        bearer = client.post(
            "/rotate", headers={"Authorization": "Bearer abc"}, cookies=cookies
        )
        basic = client.post(
            "/rotate", headers={"Authorization": "Basic YTpi"}, cookies=cookies
        )
        none = client.post("/rotate", cookies=cookies)

        assert bearer.status_code == 200
        assert (basic.status_code, none.status_code) == (403, 403)

    def test_safe_methods_are_not_checked(self, mount: Callable[..., _World]) -> None:
        assert self._bare(mount()).get("/touch").status_code == 200


CALLBACK = "/auth/callback/acme"
WINDOW = timedelta(minutes=5)


def _fixed_limiter() -> _SharedLimiter:
    return _SharedLimiter(InMemoryRateLimiter(clock=lambda: 1000.0))


def _from(world: _World, address: str) -> TestClient:
    """A browser whose connection comes from *address*."""
    return _Browser(
        world.app, base_url=BASE_URL, follow_redirects=False, client=(address, 50000)
    )


def _attempt(client: TestClient, username: str = "ada", **headers: str) -> Any:
    return client.post(
        "/auth/login/password",
        json={"username": username, "password": "bad"},
        headers=headers,
    )


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("audit event=")
    ]


@pytest.mark.security_control("rate-limiting")
class TestRateLimits:
    def test_password_login_is_limited_per_account(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(
            limiter=_fixed_limiter(), password_account_limit=RateLimit(2, WINDOW)
        )

        statuses = [_attempt(_from(world, f"10.0.0.{n}")).status_code for n in range(3)]
        other = _attempt(_from(world, "10.0.0.9"), username="grace")

        assert statuses == [401, 401, 429]
        assert other.status_code == 401

    def test_the_account_is_counted_whatever_its_case_or_padding(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(
            limiter=_fixed_limiter(), password_account_limit=RateLimit(1, WINDOW)
        )

        _attempt(_from(world, "10.0.0.1"), username="ada")

        assert _attempt(_from(world, "10.0.0.2"), username=" ADA ").status_code == 429

    def test_password_login_is_limited_per_client(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(
            limiter=_fixed_limiter(), password_client_limit=RateLimit(2, WINDOW)
        )
        client = _from(world, "10.0.0.1")

        statuses = [_attempt(client, username=f"user{n}").status_code for n in range(3)]
        elsewhere = _attempt(_from(world, "10.0.0.2"))

        assert statuses == [401, 401, 429]
        assert elsewhere.status_code == 401

    def test_a_limited_request_is_a_429_problem_with_retry_after(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=_fixed_limiter(), password_client_limit=RateLimit(1, WINDOW)
        ).client
        _attempt(client)

        response = _attempt(client)

        assert response.status_code == 429
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["retry-after"] == "200"
        assert response.json()["type"] == f"{TYPE_BASE}too-many-requests"
        assert SESSION_COOKIE not in _set_cookies(response)

    def test_forwarded_for_does_not_choose_the_client_of_an_untrusted_peer(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=_fixed_limiter(), password_client_limit=RateLimit(1, WINDOW)
        ).client
        _attempt(client, **{"X-Forwarded-For": "1.1.1.1"})

        response = _attempt(client, **{"X-Forwarded-For": "2.2.2.2"})

        assert response.status_code == 429

    def test_a_trusted_proxy_names_the_client_in_forwarded_for(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(
            limiter=_fixed_limiter(),
            password_client_limit=RateLimit(1, WINDOW),
            trusted_proxies=["10.0.0.0/8"],
        )
        proxy = _from(world, "10.0.0.1")

        first = _attempt(proxy, **{"X-Forwarded-For": "1.1.1.1"})
        other = _attempt(proxy, **{"X-Forwarded-For": "2.2.2.2"})
        again = _attempt(proxy, **{"X-Forwarded-For": "1.1.1.1"})
        # A client cannot prepend a name of its own to the proxy's chain.
        spoofed = _attempt(proxy, **{"X-Forwarded-For": "9.9.9.9, 1.1.1.1"})

        assert [r.status_code for r in (first, other, again, spoofed)] == [
            401,
            401,
            429,
            429,
        ]

    def test_callbacks_are_limited_per_client(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(
            limiter=_fixed_limiter(), callback_client_limit=RateLimit(2, WINDOW)
        )
        client = _from(world, "10.0.0.1")

        statuses = [client.get(CALLBACK) for _ in range(3)]
        elsewhere = _from(world, "10.0.0.2").get(CALLBACK)

        assert [r.status_code for r in statuses] == [302, 302, 429]
        assert statuses[2].headers["retry-after"] == "200"
        assert elsewhere.status_code == 302

    def test_a_limit_of_none_is_no_limit(self, mount: Callable[..., _World]) -> None:
        client = mount(
            limiter=_fixed_limiter(),
            password_client_limit=None,
            password_account_limit=None,
        ).client

        assert {_attempt(client).status_code for _ in range(5)} == {401}

    def test_the_default_limits_are_the_same_as_djangos(
        self, mount: Callable[..., _World]
    ) -> None:
        config = mount().config

        assert config.password_client_limit == RateLimit(30, WINDOW)
        assert config.password_account_limit == RateLimit(10, WINDOW)
        assert config.callback_client_limit == RateLimit(60, WINDOW)

    def test_the_window_resets(self, mount: Callable[..., _World]) -> None:
        now = [1000.0]
        client = mount(
            limiter=_SharedLimiter(InMemoryRateLimiter(clock=lambda: now[0])),
            password_client_limit=RateLimit(1, WINDOW),
        ).client
        _attempt(client)
        assert _attempt(client).status_code == 429

        now[0] += 300

        assert _attempt(client).status_code == 401


@pytest.mark.security_control("audit-events")
class TestAudit:
    def test_login_success_and_logout(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        world = mount()
        world.password_login()
        world.client.post("/auth/logout")

        assert _events(caplog) == [
            "audit event=login.success account_id='acct-ada' provider='password'",
            "audit event=logout account_id='acct-ada' provider='password'",
        ]

    def test_login_failure_names_no_credentials(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        mount().client.post(
            "/auth/login/password",
            json={"username": "ada@example.com", "password": "hunter2"},
        )

        assert _events(caplog) == [
            "audit event=login.failure provider='password' code='login_failed' "
            "reason='invalid credentials'"
        ]
        assert "hunter2" not in caplog.text
        assert "ada@example.com" not in caplog.text

    def test_an_oidc_login_failure(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        world.idp.deny_authorization = True
        caplog.set_level(logging.INFO)

        world.sign_in_with_idp()

        assert len(_events(caplog)) == 1
        assert _events(caplog)[0].startswith(
            "audit event=login.failure provider='acme' code='access_denied'"
        )

    def test_logout_all(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        world.password_login()
        caplog.set_level(logging.INFO)

        world.client.post("/auth/logout/all")

        assert _events(caplog) == [
            "audit event=logout.all account_id='acct-ada' provider='password'"
        ]

    def test_back_channel_logout(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        caplog.set_level(logging.INFO)

        world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sid="sid-secret")},
        )
        world.client.post(
            "/auth/backchannel-logout/acme",
            data={"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert _events(caplog) == [
            "audit event=logout.backchannel provider='acme' scope='session'",
            "audit event=logout.backchannel provider='acme' scope='account' "
            "account_id='acct-u1'",
        ]
        assert "sid-secret" not in caplog.text

    def test_a_rejected_account(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        world.idp.user = {"sub": "stranger", "email": "x@example.com"}
        caplog.set_level(logging.INFO)

        world.sign_in_with_idp()

        assert _events(caplog) == [
            "audit event=account.rejected provider='acme' reason='not provisioned'",
            "audit event=login.failure provider='acme' "
            "code='account_not_provisioned' reason='not provisioned'",
        ]
        assert "x@example.com" not in caplog.text

    def test_a_disabled_account(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        world.contexts.inactive.add("acct-ada")
        caplog.set_level(logging.INFO)

        world.password_login()

        events = _events(caplog)
        assert events[0] == (
            "audit event=account.disabled account_id='acct-ada' provider='password'"
        )
        assert "login.failure" in events[1]
        assert len(events) == 2

    def test_a_provisioning_resolver_records_account_provisioned(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        class Provisioning(_Accounts):
            def resolve(self, identity: ExternalIdentity) -> str:
                account = super().resolve(identity)
                audit("account.provisioned", account_id=account, provider="acme")
                return account

        world = mount(accounts=Provisioning())
        caplog.set_level(logging.INFO)

        world.sign_in_with_idp()

        assert _events(caplog) == [
            "audit event=account.provisioned account_id='acct-u1' provider='acme'",
            "audit event=login.success account_id='acct-u1' provider='acme'",
        ]

    def test_a_rate_limited_request(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        client = mount(
            limiter=_fixed_limiter(), callback_client_limit=RateLimit(0, WINDOW)
        ).client
        caplog.set_level(logging.INFO)

        client.get(CALLBACK)

        assert _events(caplog) == [
            "audit event=rate_limited scope='callback' by='client' retry_after=200"
        ]


class TestOidcResponseChecks:
    """The adapter's checks, shown through the callback route."""

    @pytest.mark.security_control("oidc-response-checks", "token-profiles")
    @pytest.mark.parametrize(
        "fault",
        [
            "response_iss",
            "response_iss_missing",
            "wrong_nonce",
            "wrong_aud",
            "wrong_azp",
            "wrong_at_hash",
            "expired",
            "alg_none",
            "unknown_kid",
        ],
    )
    def test_a_faulty_identity_provider_response_fails_the_login(
        self,
        mount: Callable[..., _World],
        caplog: pytest.LogCaptureFixture,
        fault: str,
    ) -> None:
        world = mount()
        setattr(world.idp.faults, fault, True)
        caplog.set_level(logging.INFO)

        response = world.sign_in_with_idp()

        assert response.headers["location"] == "/auth/error?error=login_failed"
        assert SESSION_COOKIE not in _set_cookies(response)
        assert [e.split(" code=")[0] for e in _events(caplog)] == [
            "audit event=login.failure provider='acme'"
        ]

    @pytest.mark.security_control("oidc-response-checks")
    def test_a_userinfo_subject_that_differs_fails_the_login(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.idp.faults.userinfo_sub_mismatch = True

        response = world.sign_in_with_idp()

        assert response.headers["location"] == "/auth/error?error=login_failed"

    @pytest.mark.security_control("oidc-response-checks")
    def test_the_request_carries_state_nonce_and_an_s256_challenge(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()

        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})

        query = dict(parse_qsl(urlsplit(start.headers["location"]).query))
        assert query["state"]
        assert query["nonce"]
        assert query["code_challenge"]
        assert query["code_challenge_method"] == "S256"

    @pytest.mark.security_control("oidc-response-checks")
    def test_a_callback_with_another_state_fails_the_login(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        start = world.client.get("/auth/login/acme", params={"return_to": "/orders"})
        parts = urlsplit(world.approve(start.headers["location"]))
        query = {**dict(parse_qsl(parts.query)), "state": "forged"}

        response = world.client.get(f"{parts.path}?{urlencode(query)}")

        assert response.headers["location"] == "/auth/error?error=login_failed"
        assert SESSION_COOKIE not in _set_cookies(response)
