"""The offline fake IdP: FakeOidcProvider, end to end over loopback HTTP."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("authlib")

from assertpy import assert_that  # noqa: E402
from rn_forge.auth import InMemoryReplayStore  # noqa: E402
from rn_forge.auth.oidc import (  # noqa: E402
    IdTokenVerifier,
    JwtVerifier,
    LogoutTokenVerifier,
    TokenVerificationError,
    discover_oidc,
)
from rn_forge.auth.testing import FakeOidcProvider, Faults  # noqa: E402

pytestmark = pytest.mark.unit

CLIENT = "web-login"
REDIRECT = "http://127.0.0.1/callback"
VERIFIER = "v" * 64
NONCE = "n-0S6_WzA2Mj"
STATE = "st-123"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _send(request: urllib.request.Request) -> tuple[int, dict[str, str], bytes]:
    try:
        with _OPENER.open(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def _challenge(verifier: str = VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _authorize(idp: FakeOidcProvider, **overrides: str | None) -> dict[str, list[str]]:
    """Send an authorization request; return the redirect's query parameters."""
    params: dict[str, str | None] = {
        "client_id": CLIENT,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": "openid profile",
        "state": STATE,
        "nonce": NONCE,
        "code_challenge": _challenge(),
        "code_challenge_method": "S256",
        **overrides,
    }
    query = urlencode({k: v for k, v in params.items() if v is not None})
    status, headers, _ = _send(
        urllib.request.Request(f"{idp.authorization_endpoint}?{query}")
    )
    assert status == 302
    assert headers["Location"].startswith(REDIRECT)
    return parse_qs(urlsplit(headers["Location"]).query)


def _exchange(
    idp: FakeOidcProvider, code: str, *, basic: bool = False, **overrides: str
) -> tuple[int, dict[str, Any]]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
        **overrides,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if basic:
        raw = base64.b64encode(f"{CLIENT}:{idp.client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {raw}"
    else:
        form.setdefault("client_id", CLIENT)
        form.setdefault("client_secret", idp.client_secret or "")
    request = urllib.request.Request(
        idp.token_endpoint, urlencode(form).encode(), headers
    )
    status, _, body = _send(request)
    return status, json.loads(body)


def _login(idp: FakeOidcProvider) -> dict[str, Any]:
    """The whole code flow; returns the token response."""
    code = _authorize(idp)["code"][0]
    status, tokens = _exchange(idp, code)
    assert status == 200
    return tokens


def _id_token_verifier(idp: FakeOidcProvider, **kwargs: Any) -> IdTokenVerifier:
    return IdTokenVerifier.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, client_id=CLIENT, **kwargs
    )


def _userinfo(idp: FakeOidcProvider, access_token: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        idp.userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}
    )
    status, _, body = _send(request)
    return status, json.loads(body) if body else {}


@pytest.fixture
def provider():
    with FakeOidcProvider() as fake:
        yield fake


class TestLifecycle:
    def test_it_listens_on_loopback_and_stops(self) -> None:
        with FakeOidcProvider() as idp:
            assert_that(idp.issuer).starts_with("http://127.0.0.1:")
            assert_that(discover_oidc(idp.issuer).issuer).is_equal_to(idp.issuer)
        with pytest.raises(TokenVerificationError):
            discover_oidc(idp.issuer)

    def test_close_without_start_does_not_block(self) -> None:
        FakeOidcProvider().close()

    def test_the_fixture_form_works(self, provider) -> None:
        assert_that(provider.jwks_url).ends_with("/keys")


class TestDiscovery:
    def test_the_document_lists_the_endpoints_and_capabilities(self, provider) -> None:
        with urllib.request.urlopen(
            f"{provider.issuer}/.well-known/openid-configuration"
        ) as response:
            document = json.load(response)

        assert_that(document).contains_entry(
            {"issuer": provider.issuer},
            {"authorization_endpoint": provider.authorization_endpoint},
            {"token_endpoint": provider.token_endpoint},
            {"userinfo_endpoint": provider.userinfo_endpoint},
            {"jwks_uri": provider.jwks_url},
            {"end_session_endpoint": provider.end_session_endpoint},
            {"authorization_response_iss_parameter_supported": True},
            {"backchannel_logout_supported": True},
            {"code_challenge_methods_supported": ["S256"]},
        )

    def test_end_session_can_be_left_out(self, provider) -> None:
        provider.advertise_end_session = False
        with urllib.request.urlopen(
            f"{provider.issuer}/.well-known/openid-configuration"
        ) as response:
            assert_that(json.load(response)).does_not_contain_key(
                "end_session_endpoint"
            )

    def test_requests_are_recorded_with_method_and_path(self, provider) -> None:
        discover_oidc(provider.issuer)
        _login(provider)

        assert_that(
            [(r.method, r.path.removeprefix("/tenant")) for r in provider.requests]
        ).is_equal_to(
            [
                ("GET", "/.well-known/openid-configuration"),
                ("GET", "/authorize"),
                ("POST", "/token"),
            ]
        )
        assert_that(provider.fetches("/authorize")).is_equal_to(1)


class TestCodeFlow:
    def test_the_flow_returns_verifiable_tokens_and_userinfo(self, provider) -> None:
        response = _authorize(provider)
        assert_that(response["state"]).is_equal_to([STATE])
        assert_that(response["iss"]).is_equal_to([provider.issuer])

        status, tokens = _exchange(provider, response["code"][0])

        assert_that(status).is_equal_to(200)
        assert_that(tokens).contains_entry({"token_type": "Bearer"})
        assert_that(tokens["expires_in"]).is_greater_than(0)
        claims = _id_token_verifier(provider).verify(
            tokens["id_token"], nonce=NONCE, access_token=tokens["access_token"]
        )
        assert_that(claims["sub"]).is_equal_to("u1")
        assert_that(_userinfo(provider, tokens["access_token"])).is_equal_to(
            (200, {"sub": "u1", "email": "u1@example.com", "name": "User One"})
        )

    def test_auth_age_sets_the_id_token_auth_time(self, provider) -> None:
        provider.auth_age = 3600.0
        tokens = _login(provider)
        claims = _id_token_verifier(provider).verify(
            tokens["id_token"], nonce=NONCE, access_token=tokens["access_token"]
        )
        assert_that(time.time() - claims["auth_time"]).is_between(3600, 3610)

    def test_basic_client_authentication_is_accepted(self, provider) -> None:
        code = _authorize(provider)["code"][0]
        assert_that(_exchange(provider, code, basic=True)[0]).is_equal_to(200)

    def test_a_wrong_client_secret_is_rejected(self, provider) -> None:
        code = _authorize(provider)["code"][0]
        status, body = _exchange(provider, code, client_secret="nope")
        assert_that((status, body["error"])).is_equal_to((401, "invalid_client"))

    def test_a_code_is_single_use(self, provider) -> None:
        code = _authorize(provider)["code"][0]
        assert_that(_exchange(provider, code)[0]).is_equal_to(200)
        status, body = _exchange(provider, code)
        assert_that((status, body["error"])).is_equal_to((400, "invalid_grant"))

    def test_a_pkce_mismatch_is_rejected_and_spends_the_code(self, provider) -> None:
        code = _authorize(provider)["code"][0]
        status, body = _exchange(provider, code, code_verifier="x" * 64)
        assert_that((status, body["error"])).is_equal_to((400, "invalid_grant"))
        assert_that(_exchange(provider, code)[0]).is_equal_to(400)

    def test_a_different_redirect_uri_is_rejected(self, provider) -> None:
        code = _authorize(provider)["code"][0]
        status, _ = _exchange(provider, code, redirect_uri="http://127.0.0.1/other")
        assert_that(status).is_equal_to(400)

    def test_an_unknown_grant_type_is_rejected(self, provider) -> None:
        status, body = _exchange(provider, "c", grant_type="password")
        assert_that((status, body["error"])).is_equal_to(
            (400, "unsupported_grant_type")
        )

    @pytest.mark.parametrize(
        "override",
        [
            {"response_type": "token"},
            {"state": None},
            {"nonce": None},
            {"code_challenge": None},
            {"code_challenge_method": "plain"},
            {"scope": "profile"},
        ],
    )
    def test_an_invalid_authorization_request_redirects_with_an_error(
        self, provider, override
    ) -> None:
        response = _authorize(provider, **override)
        assert_that(response["error"]).is_equal_to(["invalid_request"])
        assert_that(response).does_not_contain_key("code")

    @pytest.mark.parametrize(
        "override",
        [{"client_id": "other"}, {"redirect_uri": "http://evil.example/cb"}],
    )
    def test_an_unknown_client_or_redirect_is_not_redirected_to(
        self, provider, override
    ) -> None:
        query = urlencode(
            {
                "client_id": CLIENT,
                "redirect_uri": REDIRECT,
                "response_type": "code",
                "scope": "openid",
                "state": STATE,
                "nonce": NONCE,
                "code_challenge": _challenge(),
                "code_challenge_method": "S256",
                **override,
            }
        )
        status, headers, _ = _send(
            urllib.request.Request(f"{provider.authorization_endpoint}?{query}")
        )
        assert_that(status).is_equal_to(400)
        assert_that(headers).does_not_contain_key("Location")

    def test_a_denied_authorization_redirects_with_access_denied(
        self, provider
    ) -> None:
        provider.deny_authorization = True
        response = _authorize(provider)
        assert_that(response["error"]).is_equal_to(["access_denied"])
        assert_that(response["state"]).is_equal_to([STATE])
        assert_that(response["iss"]).is_equal_to([provider.issuer])

    def test_userinfo_rejects_an_unknown_bearer(self, provider) -> None:
        assert_that(_userinfo(provider, "nope")[0]).is_equal_to(401)

    def test_the_user_is_configurable(self) -> None:
        with FakeOidcProvider(user={"sub": "alice", "email": "a@example.com"}) as idp:
            tokens = _login(idp)
            claims = _id_token_verifier(idp).verify(tokens["id_token"], nonce=NONCE)
            assert_that(claims["sub"]).is_equal_to("alice")
            assert_that(_userinfo(idp, tokens["access_token"])[1]["email"]).is_equal_to(
                "a@example.com"
            )

    def test_end_session_redirects_to_the_post_logout_uri(self, provider) -> None:
        query = urlencode({"post_logout_redirect_uri": REDIRECT})
        status, headers, _ = _send(
            urllib.request.Request(f"{provider.end_session_endpoint}?{query}")
        )
        assert_that((status, headers["Location"])).is_equal_to((302, REDIRECT))


class TestKeys:
    def test_rotation_adds_a_current_key_the_client_picks_up(self, provider) -> None:
        verifier = _id_token_verifier(provider, cooldown_duration=0.0)
        first = provider.current_kid
        assert_that(verifier.verify(_login(provider)["id_token"], nonce=NONCE))

        second = provider.rotate_key()
        tokens = _login(provider)

        assert_that(second).is_not_equal_to(first)
        assert_that(provider.keys).contains_key(first, second)
        header = json.loads(
            base64.urlsafe_b64decode(tokens["id_token"].split(".")[0] + "==")
        )
        assert_that(header["kid"]).is_equal_to(second)
        assert_that(
            verifier.verify(tokens["id_token"], nonce=NONCE)["sub"]
        ).is_equal_to("u1")

    def test_retiring_the_old_key_removes_it_from_the_key_set(self, provider) -> None:
        old = provider.current_kid
        old_token = provider.sign({"iss": provider.issuer, "aud": CLIENT})
        new = provider.rotate_key(retire_old=True)

        assert_that(provider.keys).contains_key(new).does_not_contain_key(old)
        verifier = _id_token_verifier(provider, cooldown_duration=0.0)
        with pytest.raises(TokenVerificationError):
            verifier.verify(old_token, nonce=NONCE)

    def test_a_published_key_is_listed_but_not_used_for_signing(self, provider) -> None:
        current = provider.current_kid
        provider.publish("extra")
        assert_that(provider.keys).contains_key("extra")
        assert_that(provider.current_kid).is_equal_to(current)


class TestTokens:
    def test_sign_omits_none_claims_and_typ(self, provider) -> None:
        import jwt

        token = provider.sign({"a": 1, "b": None})
        assert_that(jwt.get_unverified_header(token)).does_not_contain_key("typ")
        assert_that(jwt.decode(token, options={"verify_signature": False})).is_equal_to(
            {"a": 1}
        )

    def test_sign_can_name_typ_and_kid(self, provider) -> None:
        import jwt

        provider.publish("k9")
        header = jwt.get_unverified_header(
            provider.sign({"a": 1}, typ="x+jwt", kid="k9")
        )
        assert_that(header).contains_entry({"typ": "x+jwt"}, {"kid": "k9"})

    def test_an_rfc9068_access_token_passes_the_rfc9068_profile(self, provider) -> None:
        verifier = JwtVerifier.from_jwks_url(
            provider.jwks_url,
            issuer=provider.issuer,
            audience="api://orders",
            mode="rfc9068",
        )
        claims = verifier.verify(provider.access_token(scope="orders:read"))
        assert_that(claims).contains_entry(
            {"scope": "orders:read"}, {"client_id": CLIENT}
        )

    def test_an_rfc7519_access_token_passes_the_rfc7519_profile(self, provider) -> None:
        verifier = JwtVerifier.from_jwks_url(
            provider.jwks_url,
            issuer=provider.issuer,
            audience="api://orders",
            mode="rfc7519",
        )
        assert_that(
            verifier.verify(provider.access_token(profile="rfc7519"))["sub"]
        ).is_equal_to("u1")

    def test_the_two_profiles_do_not_accept_each_others_tokens(self, provider) -> None:
        strict = JwtVerifier.from_jwks_url(
            provider.jwks_url,
            issuer=provider.issuer,
            audience="api://orders",
            mode="rfc9068",
        )
        token = provider.access_token(profile="rfc7519")
        with pytest.raises(TokenVerificationError):
            strict.verify(token)

    def test_a_logout_token_passes_the_logout_profile(self, provider) -> None:
        verifier = LogoutTokenVerifier.from_jwks_url(
            provider.jwks_url,
            issuer=provider.issuer,
            client_id=CLIENT,
            replay_store=InMemoryReplayStore(),
        )
        claims = verifier.verify(provider.logout_token(sid="s1"))
        assert_that(claims).contains_entry({"sid": "s1"}).does_not_contain_key("sub")
        assert_that(
            verifier.verify(provider.logout_token(sub="u1"))["sub"]
        ).is_equal_to("u1")

    def test_logout_tokens_have_distinct_jti_values(self, provider) -> None:
        import jwt

        jtis = {
            jwt.decode(
                provider.logout_token(sid="s"), options={"verify_signature": False}
            )["jti"]
            for _ in range(3)
        }
        assert_that(jtis).is_length(3)

    def test_a_logout_token_needs_a_sid_or_a_sub(self, provider) -> None:
        with pytest.raises(ValueError, match="sid or a sub"):
            provider.logout_token()


class TestFaults:
    """Each switch is off by default and, on, makes the response faulty."""

    def test_nothing_is_on_by_default(self, provider) -> None:
        assert_that(provider.faults).is_equal_to(Faults())
        tokens = _login(provider)
        _id_token_verifier(provider).verify(
            tokens["id_token"], nonce=NONCE, access_token=tokens["access_token"]
        )
        assert_that(discover_oidc(provider.issuer).issuer).is_equal_to(provider.issuer)

    def test_userinfo_error_answers_500(self, provider) -> None:
        tokens = _login(provider)
        provider.faults.userinfo_error = True
        assert_that(_userinfo(provider, tokens["access_token"])[0]).is_equal_to(500)

    def test_oauth2_only_needs_no_openid_scope_or_nonce_and_issues_no_id_token(
        self, provider
    ) -> None:
        provider.oauth2_only = True
        response = _authorize(provider, scope="read:user", nonce=None)
        status, tokens = _exchange(provider, response["code"][0])
        assert_that(status).is_equal_to(200)
        assert_that(tokens).does_not_contain_key("id_token")
        assert_that(_userinfo(provider, tokens["access_token"])[0]).is_equal_to(200)

    def test_discovery_issuer_is_rejected_by_discovery(self, provider) -> None:
        provider.faults.discovery_issuer = True
        with pytest.raises(TokenVerificationError, match="does not match"):
            discover_oidc(provider.issuer)

    def test_response_iss_names_another_issuer(self, provider) -> None:
        # No pykit check yet: the F13.4 adapter compares it (RFC 9207).
        provider.faults.response_iss = True
        iss = _authorize(provider)["iss"]
        assert_that(iss).is_length(1)
        assert_that(iss[0]).is_not_equal_to(provider.issuer)

    def test_response_iss_missing_drops_the_parameter(self, provider) -> None:
        # No pykit check yet: the F13.4 adapter requires it (RFC 9207).
        provider.faults.response_iss_missing = True
        response = _authorize(provider)
        assert_that(response).contains_key("code").does_not_contain_key("iss")

    def test_response_iss_missing_applies_to_error_responses(self, provider) -> None:
        provider.faults.response_iss_missing = True
        provider.deny_authorization = True
        assert_that(_authorize(provider)).does_not_contain_key("iss")

    def test_userinfo_sub_mismatch_differs_from_the_id_token(self, provider) -> None:
        # No pykit check yet: the F13.4 adapter compares the two subjects.
        provider.faults.userinfo_sub_mismatch = True
        tokens = _login(provider)
        sub = _id_token_verifier(provider).verify(tokens["id_token"], nonce=NONCE)[
            "sub"
        ]
        userinfo = _userinfo(provider, tokens["access_token"])[1]
        assert_that(userinfo["sub"]).is_not_equal_to(sub)

    @pytest.mark.parametrize(
        ("fault", "message"),
        [
            ("wrong_nonce", "nonce"),
            ("wrong_aud", "aud"),
            ("wrong_azp", "azp"),
            ("wrong_at_hash", "at_hash"),
            ("expired", "expired"),
            ("alg_none", "algorithm"),
            ("unknown_kid", "kid|Unable to find"),
        ],
    )
    def test_the_id_token_verifier_rejects_each_id_token_fault(
        self, provider, fault, message
    ) -> None:
        setattr(provider.faults, fault, True)
        tokens = _login(provider)

        verifier = _id_token_verifier(provider)

        with pytest.raises(TokenVerificationError, match=f"(?i){message}"):
            verifier.verify(
                tokens["id_token"], nonce=NONCE, access_token=tokens["access_token"]
            )

    def test_wrong_azp_lists_both_clients_in_aud(self, provider) -> None:
        import jwt

        provider.faults.wrong_azp = True
        claims = jwt.decode(
            _login(provider)["id_token"], options={"verify_signature": False}
        )
        assert_that(claims["aud"]).contains(CLIENT).is_length(2)
        assert_that(claims["azp"]).is_not_equal_to(CLIENT)

    def test_expired_is_in_the_past(self, provider) -> None:
        import jwt

        provider.faults.expired = True
        claims = jwt.decode(
            _login(provider)["id_token"], options={"verify_signature": False}
        )
        assert_that(claims["exp"]).is_less_than(time.time())
