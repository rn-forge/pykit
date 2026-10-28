from __future__ import annotations

import logging
import sys
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from contextlib import AbstractContextManager, nullcontext
from itertools import count
from typing import ClassVar
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from django.http import HttpRequest, HttpResponse
from django.urls import path
from rest_framework.authentication import BaseAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections
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
    CSRF_MIDDLEWARE,
    CSRF_SETTINGS,
    SESSION_COOKIE,
    SESSION_SETTINGS,
    Sessions,
    rotate_session,
    TRANSACTION_COOKIE,
    AuthRoutesConfig,
    CacheReplayStore,
    CacheTransactionStore,
    FixedWindowLimiter,
    RateLimit,
    auth_urlpatterns,
    enforce_csrf,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

CALLBACK = "/auth/callback/acme"
TYPE_BASE = "https://errors.example/"
DB_ENGINE = "django.contrib.sessions.backends.db"


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


class _CsrfAuthentication(BaseAuthentication):
    """What a DRF session authentication class does for the requests it accepts."""

    def authenticate(self, request: Any) -> None:
        enforce_csrf(request._request)


class _GuardedView(APIView):
    authentication_classes = [_CsrfAuthentication]
    permission_classes: list[Any] = []

    def get(self, request: Any) -> Response:
        return Response({})

    def post(self, request: Any) -> Response:
        return Response({})


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
    idp: FakeOidcProvider, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Callable[..., _World]]:
    stack = ExitStack()

    def build(
        *,
        debug: bool = False,
        prefix: str = "auth",
        rp_initiated_logout: bool = False,
        session_engine: str = DB_ENGINE,
        django_settings: dict[str, Any] | None = None,
        **overrides: Any,
    ) -> _World:
        stack.enter_context(
            override_settings(
                DEBUG=debug,
                USE_TZ=True,
                MIDDLEWARE=[
                    "django.contrib.sessions.middleware.SessionMiddleware",
                    CSRF_MIDDLEWARE,
                ],
                RN_FORGE_DJANGO={"AUTH": {"PROBLEM_TYPE_BASE": TYPE_BASE}},
                CACHES={
                    "default": {
                        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                        "LOCATION": str(tmp_path / "cache"),
                    }
                },
                REST_FRAMEWORK={
                    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
                },
                **CSRF_SETTINGS,
                **(django_settings or {}),
                **{**SESSION_SETTINGS, "SESSION_ENGINE": session_engine},
            )
        )
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
        contexts = _Contexts()
        config = AuthRoutesConfig(
            providers=providers,
            accounts=accounts,
            contexts=contexts,
            account_state=_State(contexts),
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
        sessions = Sessions(
            contexts=contexts,
            replay=config.replay,
            idle_timeout=config.idle_timeout,
            absolute_timeout=config.absolute_timeout,
        )

        def touch(request: HttpRequest) -> HttpResponse:
            active = sessions.read(request)
            return HttpResponse(status=200 if active else 401)

        def rotate(request: HttpRequest) -> HttpResponse:
            rotate_session(request)
            return HttpResponse()

        module = ModuleType("test_routes_urlconf")
        module.urlpatterns = [  # type: ignore[attr-defined]
            *auth_urlpatterns(config, prefix=prefix),
            path("touch", touch),
            path("bearer", lambda request: HttpResponse()),
            path("drf", _GuardedView.as_view()),
            path("rotate", rotate),
        ]
        monkeypatch.setitem(sys.modules, module.__name__, module)
        stack.enter_context(override_settings(ROOT_URLCONF=module.__name__))
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


class _Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)

    def advance(self, **kwargs: float) -> None:
        self.moment += timedelta(**kwargs)

    def now(self) -> datetime:
        return self.moment


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr("django.utils.timezone.now", fake.now)
    monkeypatch.setattr(Sessions, "now", staticmethod(fake.now))
    return fake


def _password_login(client: Client) -> Any:
    return client.post(
        "/auth/login/password",
        {"username": "ada", "password": "correct"},
        content_type="application/json",
    )


def _session_key(client: Client) -> str:
    return client.cookies[SESSION_COOKIE].value


def _sid(client: Client) -> str:
    """The IdP session ID the login recorded in the client's session."""
    session_ref = SessionStore(_session_key(client)).load()["rn_forge_auth"][
        "session_ref"
    ]
    assert isinstance(session_ref, str)
    return session_ref


class TestCachedDbEngine:
    def test_the_production_engine_logs_in_and_out(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount(session_engine="django.contrib.sessions.backends.cached_db")
        _password_login(world.client)
        assert world.client.get("/auth/session").status_code == 200

        world.client.post("/auth/logout")

        assert world.client.get("/auth/session").status_code == 401


class TestSessionContent:
    def test_the_cookie_has_the_designs_flags(
        self, mount: Callable[..., _World]
    ) -> None:
        cookie = _password_login(mount().client).cookies[SESSION_COOKIE]

        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Lax"
        assert cookie["path"] == "/"
        assert cookie["domain"] == ""

    def test_the_session_holds_only_the_designs_content(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)

        data = SessionStore(_session_key(world.client)).load()

        assert set(data) == {"rn_forge_auth", "_session_expiry"}
        assert set(data["rn_forge_auth"]) == {
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

    def test_login_gives_a_new_session_id(self, mount: Callable[..., _World]) -> None:
        world = mount()
        anonymous = world.client.session
        anonymous["seen"] = 1
        anonymous.save()
        world.client.cookies[SESSION_COOKIE] = anonymous.session_key
        before = _session_key(world.client)

        _password_login(world.client)

        assert _session_key(world.client) != before
        assert not SessionStore(before).exists(before)

    def test_rotate_session_changes_the_id_and_keeps_the_login(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)
        before = _session_key(world.client)

        world.client.get("/rotate")

        after = _session_key(world.client)
        assert after != before
        assert world.client.get("/auth/session").status_code == 200
        stale = Client()
        stale.cookies[SESSION_COOKIE] = before
        assert stale.get("/auth/session").status_code == 401


class TestTimeouts:
    def test_an_idle_session_expires_after_30_minutes(
        self, mount: Callable[..., _World], clock: _Clock
    ) -> None:
        world = mount()
        _password_login(world.client)

        clock.advance(minutes=29)
        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=2)

        assert world.client.get("/auth/session").status_code == 401

    def test_a_normal_request_slides_the_idle_expiry(
        self, mount: Callable[..., _World], clock: _Clock
    ) -> None:
        world = mount()
        _password_login(world.client)

        for _ in range(3):
            clock.advance(minutes=20)
            assert world.client.get("/touch").status_code == 200

        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=31)
        assert world.client.get("/auth/session").status_code == 401

    def test_get_session_does_not_extend_the_session(
        self, mount: Callable[..., _World], clock: _Clock
    ) -> None:
        world = mount()
        _password_login(world.client)

        clock.advance(minutes=20)
        assert world.client.get("/auth/session").status_code == 200
        clock.advance(minutes=15)

        assert world.client.get("/auth/session").status_code == 401

    def test_the_absolute_timeout_ends_an_active_session(
        self, mount: Callable[..., _World], clock: _Clock
    ) -> None:
        world = mount()
        _password_login(world.client)

        for _ in range(35):
            clock.advance(minutes=20)
            assert world.client.get("/touch").status_code == 200
        body = world.client.get("/auth/session").json()
        assert body["expiresAt"] == "2026-10-28T21:00:00Z"
        clock.advance(minutes=21)

        assert world.client.get("/auth/session").status_code == 401

    def test_the_timeouts_are_configurable(
        self, mount: Callable[..., _World], clock: _Clock
    ) -> None:
        world = mount(idle_timeout=timedelta(minutes=5))
        _password_login(world.client)

        clock.advance(minutes=6)

        assert world.client.get("/auth/session").status_code == 401


class TestRevocation:
    def _row_exists(self, key: str) -> bool:
        return Session.objects.filter(session_key=key).exists()

    def test_a_version_mismatch_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)
        key = _session_key(world.client)
        world.state.bump_session_version("acct-ada")

        response = world.client.get("/auth/session")

        assert response.status_code == 401
        assert not self._row_exists(key)

    def test_a_disabled_account_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)
        key = _session_key(world.client)
        world.contexts.inactive.add("acct-ada")

        assert world.client.get("/auth/session").status_code == 401
        assert not self._row_exists(key)

    def test_a_revoked_sid_deletes_the_session_and_answers_401(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        key = _session_key(world.client)
        assert world.client.get("/auth/session").status_code == 200

        world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sid=_sid(world.client))},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert not self._row_exists(key)

    def test_logout_ends_this_session_only(self, mount: Callable[..., _World]) -> None:
        world = mount()
        other = Client()
        _password_login(world.client)
        _password_login(other)

        world.client.post("/auth/logout")

        assert world.client.get("/auth/session").status_code == 401
        assert other.get("/auth/session").status_code == 200

    def test_logout_all_ends_every_session_of_the_account(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        other = Client()
        _password_login(world.client)
        _password_login(other)

        world.client.post("/auth/logout/all")

        assert other.get("/auth/session").status_code == 401

    def test_a_sid_backchannel_logout_ends_that_session_only(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        other = Client()
        _password_login(other)

        world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sid=_sid(world.client))},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert other.get("/auth/session").status_code == 200

    def test_a_sub_backchannel_logout_ends_every_session_of_the_account(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()
        second = Client()
        start = second.get("/auth/login/acme", {"return_to": "/orders"})
        second.get(world.approve(start["Location"]))

        world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert world.client.get("/auth/session").status_code == 401
        assert second.get("/auth/session").status_code == 401


WORKERS = 4
REQUESTS_PER_PHASE = 3


def _race(
    world: _World, revoke: Callable[[], None], *, serialize: bool
) -> tuple[int, int]:
    """Hammer the session routes from threads while *revoke* runs.

    The workers alternate ``GET /auth/session`` with a request that extends the
    session, so a request in flight at the revocation may write the session
    back. A request that began after *revoke* returned must not succeed, and a
    fresh request at the end must be refused. Returns the number of requests
    seen before and after the revocation.

    With *serialize*, requests take turns on the database, because sqlite's
    shared in-memory database refuses concurrent access with "table is
    locked"; which thread runs next is still up to the scheduler.
    """
    revoked = threading.Event()
    stop = threading.Event()
    barrier = threading.Barrier(WORKERS + 1)
    lock = threading.Lock()
    database: AbstractContextManager[object] = (
        threading.Lock() if serialize else nullcontext()
    )
    seen: list[tuple[bool, int]] = []

    def worker() -> None:
        client = Client()
        client.cookies[SESSION_COOKIE] = _session_key(world.client)
        barrier.wait()
        try:
            for turn in count():
                if stop.is_set():
                    break
                after = revoked.is_set()
                with database:
                    status = client.get(
                        "/touch" if turn % 2 else "/auth/session"
                    ).status_code
                with lock:
                    seen.append((after, status))
        finally:
            connections.close_all()

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
    with database:
        revoke()
    revoked.set()
    wait_for(True)
    stop.set()
    for thread in threads:
        thread.join()
    assert [status for after, status in seen if after and status == 200] == []
    # A request in flight at a logout can find its session gone mid-save (400).
    assert {status for after, status in seen if not after} <= {200, 400, 401}
    stale = Client()
    stale.cookies[SESSION_COOKIE] = _session_key(world.client)
    assert stale.get("/auth/session").status_code == 401
    return (
        sum(1 for after, _ in seen if not after),
        sum(1 for after, _ in seen if after),
    )


class _RaceScenarios:
    serialize: ClassVar[bool]

    def test_no_request_succeeds_after_a_logout(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)

        before, after = _race(
            world,
            lambda: world.client.post("/auth/logout"),
            serialize=self.serialize,
        )

        assert before and after

    def test_no_request_succeeds_after_a_backchannel_logout(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        world.sign_in_with_idp()

        def revoke() -> None:
            response = Client().post(
                "/auth/backchannel-logout/acme",
                {"logout_token": world.idp.logout_token(sid=_sid(world.client))},
            )
            assert response.status_code == 200

        before, after = _race(world, revoke, serialize=self.serialize)

        assert before and after

    def test_no_request_succeeds_after_an_account_is_disabled(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        _password_login(world.client)

        before, after = _race(
            world,
            lambda: world.contexts.inactive.add("acct-ada"),
            serialize=self.serialize,
        )

        assert before and after


@pytest.mark.django_db(transaction=True)
class TestRevocationRaces(_RaceScenarios):
    serialize = True


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
class TestRevocationRacesOnPostgres(_RaceScenarios):
    """The same races with real concurrency: no request lock."""

    serialize = False

    @pytest.fixture(autouse=True)
    def _require_postgres(self) -> None:
        if connection.vendor != "postgresql":
            pytest.skip("real concurrency needs PostgreSQL")


def _bare_config() -> AuthRoutesConfig:
    contexts = _Contexts()
    return AuthRoutesConfig(
        providers={},
        accounts=_Accounts(),
        contexts=contexts,
        account_state=_State(contexts),
    )


class TestSettingsChecks:
    @pytest.fixture(autouse=True)
    def _csrf_settings(self) -> Iterator[None]:
        with override_settings(
            MIDDLEWARE=[CSRF_MIDDLEWARE],
            RN_FORGE_DJANGO={"AUTH": {"PROBLEM_TYPE_BASE": TYPE_BASE}},
            **CSRF_SETTINGS,
        ):
            yield

    def test_mounting_without_a_problem_type_base_is_refused(self) -> None:
        with override_settings(RN_FORGE_DJANGO={}):
            with pytest.raises(ImproperlyConfigured, match="PROBLEM_TYPE_BASE"):
                auth_urlpatterns(_bare_config())

    def test_the_csrf_middleware_is_required_in_every_mode(self) -> None:
        with override_settings(DEBUG=True, MIDDLEWARE=[]):
            with pytest.raises(ImproperlyConfigured, match="MIDDLEWARE"):
                auth_urlpatterns(_bare_config())

    @pytest.mark.parametrize(
        "setting, value",
        [
            ("CSRF_COOKIE_NAME", "csrftoken"),
            ("CSRF_HEADER_NAME", "HTTP_X_CSRFTOKEN"),
            ("CSRF_COOKIE_HTTPONLY", True),
            ("CSRF_USE_SESSIONS", True),
            ("CSRF_FAILURE_VIEW", "django.views.csrf.csrf_failure"),
        ],
    )
    def test_the_csrf_names_are_required_in_every_mode(
        self, setting: str, value: object
    ) -> None:
        with override_settings(DEBUG=True, **{setting: value}):
            with pytest.raises(ImproperlyConfigured, match=setting):
                auth_urlpatterns(_bare_config())

    def test_a_non_secure_csrf_cookie_is_refused_outside_debug_only(self) -> None:
        with override_settings(DEBUG=True, CSRF_COOKIE_SECURE=False):
            assert auth_urlpatterns(_bare_config())

    def test_the_signed_cookie_engine_is_refused_outside_debug(self) -> None:
        with override_settings(
            DEBUG=False,
            SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        ):
            with pytest.raises(ImproperlyConfigured, match="signed-cookie"):
                auth_urlpatterns(_bare_config())

    def test_the_local_memory_cache_is_refused_outside_debug(self) -> None:
        with override_settings(DEBUG=False, **SESSION_SETTINGS):
            with pytest.raises(ImproperlyConfigured, match="local-memory"):
                auth_urlpatterns(_bare_config())

    def test_a_local_memory_session_cache_is_refused_outside_debug(
        self, tmp_path: Path
    ) -> None:
        caches = {
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": str(tmp_path),
            },
            "sessions": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            },
        }
        with override_settings(
            DEBUG=False,
            CACHES=caches,
            SESSION_CACHE_ALIAS="sessions",
            **SESSION_SETTINGS,
        ):
            with pytest.raises(ImproperlyConfigured, match="'sessions'"):
                auth_urlpatterns(_bare_config())

    @pytest.mark.parametrize(
        "setting, value",
        [
            ("SESSION_COOKIE_NAME", "sessionid"),
            ("SESSION_COOKIE_SECURE", False),
            ("SESSION_COOKIE_HTTPONLY", False),
            ("SESSION_COOKIE_SAMESITE", "Strict"),
            ("SESSION_COOKIE_DOMAIN", "example.com"),
        ],
    )
    def test_other_cookie_settings_are_refused_outside_debug(
        self, tmp_path: Path, setting: str, value: object
    ) -> None:
        caches = {
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": str(tmp_path),
            }
        }
        with override_settings(
            DEBUG=False, CACHES=caches, **{**SESSION_SETTINGS, setting: value}
        ):
            with pytest.raises(ImproperlyConfigured, match=setting):
                auth_urlpatterns(_bare_config())

    @pytest.mark.parametrize(
        "engine",
        [
            "django.contrib.sessions.backends.cache",
            "django.contrib.sessions.backends.file",
        ],
    )
    def test_any_other_engine_is_refused_outside_debug(self, engine: str) -> None:
        with override_settings(
            DEBUG=False, **{**SESSION_SETTINGS, "SESSION_ENGINE": engine}
        ):
            with pytest.raises(ImproperlyConfigured, match="not supported"):
                auth_urlpatterns(_bare_config())

    def test_debug_allows_the_development_settings(self) -> None:
        with override_settings(
            DEBUG=True,
            SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        ):
            assert auth_urlpatterns(_bare_config())

    def test_saving_every_request_is_refused_in_every_mode(self) -> None:
        with override_settings(DEBUG=True, SESSION_SAVE_EVERY_REQUEST=True):
            with pytest.raises(ImproperlyConfigured, match="SAVE_EVERY_REQUEST"):
                auth_urlpatterns(_bare_config())


class TestCsrf:
    @staticmethod
    def _client(world: _World) -> Client:
        client = Client(enforce_csrf_checks=True)
        world.client = client
        return client

    @staticmethod
    def _token(client: Client) -> str:
        """Fetch the CSRF cookie from ``/auth/session``, as the SPA does."""
        response = client.get("/auth/session")
        assert response.status_code == 401
        return client.cookies["XSRF-TOKEN"].value

    def _login(self, client: Client, token: str | None, **headers: str) -> Any:
        extra = {"HTTP_X_XSRF_TOKEN": token} if token else {}
        return client.post(
            "/auth/login/password",
            {"username": "ada", "password": "correct"},
            content_type="application/json",
            **extra,
            **headers,
        )

    def test_session_always_sets_a_script_readable_csrf_cookie(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())

        cookie = client.get("/auth/session").cookies["XSRF-TOKEN"]

        assert cookie.value
        assert cookie["httponly"] == ""
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Lax"
        client.post(
            "/auth/login/password",
            {"username": "ada", "password": "correct"},
            content_type="application/json",
            HTTP_X_XSRF_TOKEN=cookie.value,
        )
        assert client.get("/auth/session").cookies["XSRF-TOKEN"]["path"] == "/"

    def test_login_is_protected_before_sign_in(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        missing = self._login(client, None)
        wrong = self._login(client, "x" * 32)
        ok = self._login(client, token)

        assert (missing.status_code, wrong.status_code) == (403, 403)
        assert ok.status_code == 200

    def test_a_rejection_is_the_csrf_failed_problem(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())

        response = self._login(client, None)

        body = response.json()
        assert response.status_code == 403
        assert response["Content-Type"] == "application/problem+json"
        assert body["type"] == f"{TYPE_BASE}csrf-failed"
        assert body["detail"] == "CSRF verification failed."
        assert "WWW-Authenticate" not in response

    def test_logout_needs_the_token_and_rotates_it(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)
        self._login(client, token)
        token = client.cookies["XSRF-TOKEN"].value

        assert client.post("/auth/logout").status_code == 403
        response = client.post("/auth/logout", HTTP_X_XSRF_TOKEN=token)

        assert response.status_code == 200
        assert response.cookies["XSRF-TOKEN"].value != token

    def test_logout_all_needs_the_token(self, mount: Callable[..., _World]) -> None:
        client = self._client(mount())
        self._login(client, self._token(client))

        assert client.post("/auth/logout/all").status_code == 403

    def test_the_token_rotates_at_login(self, mount: Callable[..., _World]) -> None:
        client = self._client(mount())
        token = self._token(client)

        response = self._login(client, token)

        assert response.cookies["XSRF-TOKEN"].value != token

    def test_the_token_rotates_at_an_oidc_login(
        self, mount: Callable[..., _World]
    ) -> None:
        world = mount()
        client = self._client(world)
        token = self._token(client)

        response = world.sign_in_with_idp()

        assert response.cookies["XSRF-TOKEN"].value != token

    def test_an_untrusted_origin_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        response = self._login(client, token, HTTP_ORIGIN="https://evil.example")

        assert response.status_code == 403

    @pytest.mark.parametrize("secure", [True])
    def test_an_untrusted_referer_is_rejected_over_https(
        self, mount: Callable[..., _World], secure: bool
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        response = client.post(
            "/auth/login/password",
            {"username": "ada", "password": "correct"},
            content_type="application/json",
            secure=secure,
            HTTP_X_XSRF_TOKEN=token,
            HTTP_REFERER="https://evil.example/page",
        )

        assert response.status_code == 403

    def test_a_trusted_origin_passes(self, mount: Callable[..., _World]) -> None:
        client = self._client(
            mount(django_settings={"CSRF_TRUSTED_ORIGINS": ["https://app.example"]})
        )
        token = self._token(client)

        response = self._login(client, token, HTTP_ORIGIN="https://app.example")

        assert response.status_code == 200

    def test_cross_site_fetch_metadata_is_rejected(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        cross = self._login(client, token, HTTP_SEC_FETCH_SITE="cross-site")
        same = self._login(client, token, HTTP_SEC_FETCH_SITE="same-origin")

        assert cross.status_code == 403
        assert same.status_code == 200

    def test_cross_site_fetch_metadata_is_rejected_even_from_a_trusted_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(
            mount(django_settings={"CSRF_TRUSTED_ORIGINS": ["https://app.example"]})
        )
        token = self._token(client)

        response = self._login(
            client,
            token,
            HTTP_ORIGIN="https://app.example",
            HTTP_SEC_FETCH_SITE="cross-site",
        )

        assert response.status_code == 403

    def _forwarded(self, client: Client, token: str) -> Any:
        return self._login(
            client,
            token,
            HTTP_ORIGIN="https://app.example",
            HTTP_X_FORWARDED_HOST="app.example",
            HTTP_X_FORWARDED_PROTO="https",
        )

    def test_forged_forwarded_headers_do_not_vouch_for_an_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        assert self._forwarded(client, token).status_code == 403

    def test_a_configured_proxy_vouches_for_the_forwarded_origin(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(
            mount(
                django_settings={
                    "ALLOWED_HOSTS": ["testserver", "app.example"],
                    "USE_X_FORWARDED_HOST": True,
                    "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
                }
            )
        )
        token = self._token(client)

        assert self._forwarded(client, token).status_code == 200

    def test_a_drf_view_is_guarded_through_enforce_csrf(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())
        token = self._token(client)

        assert client.get("/drf").status_code == 200
        without = client.post("/drf")
        with_token = client.post("/drf", HTTP_X_XSRF_TOKEN=token)
        cross = client.post(
            "/drf", HTTP_X_XSRF_TOKEN=token, HTTP_SEC_FETCH_SITE="cross-site"
        )
        bearer = client.post("/drf", HTTP_AUTHORIZATION="Bearer abc")

        assert without.status_code == 403
        assert without.json()["detail"] == "CSRF verification failed."
        assert with_token.status_code == 200
        assert cross.status_code == 403
        assert bearer.status_code == 200

    def test_back_channel_logout_is_exempt(self, mount: Callable[..., _World]) -> None:
        world = mount()
        client = self._client(world)

        response = client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sid="sid-x")},
        )

        assert response.status_code == 200

    def test_a_request_with_a_bearer_authorization_header_is_exempt(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())

        response = client.post("/bearer", HTTP_AUTHORIZATION="Bearer abc")
        without = client.post("/bearer")

        assert response.status_code == 200
        assert without.status_code == 403

    def test_a_basic_authorization_header_is_not_exempt(
        self, mount: Callable[..., _World]
    ) -> None:
        client = self._client(mount())

        response = client.post("/bearer", HTTP_AUTHORIZATION="Basic YTpi")

        assert response.status_code == 403


FIXED_LIMITER = FixedWindowLimiter(clock=lambda: 1000.0)
WINDOW = timedelta(minutes=5)


class TestRateLimits:
    def _attempt(
        self,
        client: Client,
        username: str = "ada",
        address: str = "10.0.0.1",
        **extra: str,
    ) -> Any:
        return client.post(
            "/auth/login/password",
            {"username": username, "password": "bad"},
            content_type="application/json",
            REMOTE_ADDR=address,
            **extra,
        )

    def test_password_login_is_limited_per_account(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, password_account_limit=RateLimit(2, WINDOW)
        ).client

        statuses = [self._attempt(client, address=f"10.0.0.{n}") for n in range(3)]
        other = self._attempt(client, username="grace", address="10.0.0.9")

        assert [r.status_code for r in statuses] == [401, 401, 429]
        assert other.status_code == 401

    def test_password_login_is_limited_per_client(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, password_client_limit=RateLimit(2, WINDOW)
        ).client

        statuses = [self._attempt(client, username=f"user{n}") for n in range(3)]
        elsewhere = self._attempt(client, address="10.0.0.2")

        assert [r.status_code for r in statuses] == [401, 401, 429]
        assert elsewhere.status_code == 401

    def test_a_limited_request_is_a_429_problem_with_retry_after(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, password_client_limit=RateLimit(1, WINDOW)
        ).client
        self._attempt(client)

        response = self._attempt(client)

        assert response.status_code == 429
        assert response["Content-Type"] == "application/problem+json"
        assert response["Retry-After"] == "200"
        assert response.json()["type"] == f"{TYPE_BASE}too-many-requests"

    def test_forwarded_for_does_not_choose_the_client(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, password_client_limit=RateLimit(1, WINDOW)
        ).client
        self._attempt(client, HTTP_X_FORWARDED_FOR="1.1.1.1")

        response = self._attempt(client, HTTP_X_FORWARDED_FOR="2.2.2.2")

        assert response.status_code == 429

    def test_callbacks_are_limited_per_client(
        self, mount: Callable[..., _World]
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, callback_client_limit=RateLimit(2, WINDOW)
        ).client

        statuses = [client.get(CALLBACK, REMOTE_ADDR="10.0.0.1") for _ in range(3)]
        elsewhere = client.get(CALLBACK, REMOTE_ADDR="10.0.0.2")

        assert [r.status_code for r in statuses] == [302, 302, 429]
        assert statuses[2]["Retry-After"] == "200"
        assert elsewhere.status_code == 302

    def test_a_limit_of_none_is_no_limit(self, mount: Callable[..., _World]) -> None:
        client = mount(
            limiter=FIXED_LIMITER,
            password_client_limit=None,
            password_account_limit=None,
        ).client

        assert {self._attempt(client).status_code for _ in range(5)} == {401}

    def test_the_window_resets(self, mount: Callable[..., _World]) -> None:
        now = [1000.0]
        client = mount(
            limiter=FixedWindowLimiter(clock=lambda: now[0]),
            password_client_limit=RateLimit(1, WINDOW),
        ).client
        self._attempt(client)
        assert self._attempt(client).status_code == 429

        now[0] += 300

        assert self._attempt(client).status_code == 401


class TestAudit:
    @staticmethod
    def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
        return [
            record.getMessage()
            for record in caplog.records
            if record.getMessage().startswith("audit event=")
        ]

    def test_login_success_and_logout(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        world = mount()
        _password_login(world.client)
        world.client.post("/auth/logout")

        assert self._events(caplog) == [
            "audit event=login.success account_id='acct-ada' provider='password'",
            "audit event=logout account_id='acct-ada' provider='password'",
        ]

    def test_login_failure_names_no_credentials(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        world = mount()
        world.client.post(
            "/auth/login/password",
            {"username": "ada@example.com", "password": "hunter2"},
            content_type="application/json",
        )

        events = self._events(caplog)
        assert events == [
            "audit event=login.failure provider='password' code='login_failed' "
            "reason='invalid credentials'"
        ]
        assert "hunter2" not in caplog.text
        assert "ada@example.com" not in caplog.text

    def test_logout_all(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        _password_login(world.client)
        caplog.set_level(logging.INFO)

        world.client.post("/auth/logout/all")

        assert self._events(caplog) == [
            "audit event=logout.all account_id='acct-ada' provider='password'"
        ]

    def test_back_channel_logout(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        world = mount()
        caplog.set_level(logging.INFO)

        world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sid="sid-secret")},
        )
        world.client.post(
            "/auth/backchannel-logout/acme",
            {"logout_token": world.idp.logout_token(sub="u1")},
        )

        assert self._events(caplog) == [
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

        assert self._events(caplog) == [
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

        _password_login(world.client)

        assert self._events(caplog)[0] == (
            "audit event=account.disabled account_id='acct-ada' provider='password'"
        )
        assert "login.failure" in self._events(caplog)[1]

    def test_a_rate_limited_request(
        self, mount: Callable[..., _World], caplog: pytest.LogCaptureFixture
    ) -> None:
        client = mount(
            limiter=FIXED_LIMITER, callback_client_limit=RateLimit(0, WINDOW)
        ).client
        caplog.set_level(logging.INFO)

        client.get(CALLBACK)

        assert self._events(caplog) == [
            "audit event=rate_limited scope='callback' by='client' retry_after=200"
        ]
