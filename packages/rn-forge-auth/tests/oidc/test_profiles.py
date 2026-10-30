"""Cross-profile and key-set tests: one key, three kinds of token."""

from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("authlib")

from rn_forge.auth import InMemoryReplayStore  # noqa: E402
from rn_forge.auth.oidc import (  # noqa: E402
    IdTokenVerifier,
    JwtVerifier,
    LogoutTokenVerifier,
    TokenVerificationError,
)

pytestmark = pytest.mark.unit

API = "api://orders"
CLIENT = "web-login"
NONCE = "n1"
EVENT = "http://schemas.openid.net/event/backchannel-logout"
KEYS = "/keys"


def _tokens(idp):
    now = int(time.time())
    base = {"iss": idp.issuer, "iat": now, "exp": now + 100}
    return {
        "access": idp.sign({**base, "aud": API, "sub": "u1"}, typ="JWT"),
        "id": idp.sign({**base, "aud": CLIENT, "sub": "u1", "nonce": NONCE}),
        "logout": idp.sign(
            {**base, "aud": CLIENT, "jti": "j1", "sid": "s1", "events": {EVENT: {}}},
            typ="logout+jwt",
        ),
    }


def _accepts(idp):
    def access(token):
        JwtVerifier.from_jwks_url(idp.jwks_url, issuer=idp.issuer, audience=API).verify(
            token
        )

    def id_token(token):
        IdTokenVerifier.from_jwks_url(
            idp.jwks_url, issuer=idp.issuer, client_id=CLIENT
        ).verify(token, nonce=NONCE)

    def logout(token):
        LogoutTokenVerifier.from_jwks_url(
            idp.jwks_url,
            issuer=idp.issuer,
            client_id=CLIENT,
            replay_store=InMemoryReplayStore(),
        ).verify(token)

    return {"access": access, "id": id_token, "logout": logout}


@pytest.mark.parametrize("kind", ["access", "id", "logout"])
def test_each_token_is_accepted_only_by_its_own_profile(idp, kind):
    tokens, profiles = _tokens(idp), _accepts(idp)
    profiles[kind](tokens[kind])
    for other, token in tokens.items():
        if other != kind:
            with pytest.raises(TokenVerificationError):
                profiles[kind](token)


def test_an_id_token_for_the_login_client_is_not_an_access_token_even_if_the_audience_matches(
    idp,
):
    # The configuration refusal exists because this would otherwise pass.
    verifier = JwtVerifier.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, audience=CLIENT
    )
    token = _tokens(idp)["id"]
    with pytest.raises(TokenVerificationError, match="nonce"):
        verifier.verify(token)


@pytest.mark.parametrize(
    "build",
    [
        lambda url: JwtVerifier.from_jwks_url(url, issuer="i", audience="a"),
        lambda url: IdTokenVerifier.from_jwks_url(url, issuer="i", client_id="c"),
        lambda url: LogoutTokenVerifier.from_jwks_url(
            url, issuer="i", client_id="c", replay_store=InMemoryReplayStore()
        ),
    ],
    ids=["access", "id", "logout"],
)
class TestJwksUrl:
    @pytest.mark.parametrize("url", ["http://idp.example.com/keys", "ftp://idp/keys"])
    def test_a_non_https_url_is_refused(self, build, url):
        with pytest.raises(TokenVerificationError, match="Refusing"):
            build(url)

    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
    def test_plain_http_to_a_local_host_is_allowed(self, build, host):
        build(f"http://{host}:9/keys")


class TestKeyCooldown:
    def test_200_unknown_kids_cause_one_fetch(self, idp):
        verifier = JwtVerifier.from_jwks_url(
            idp.jwks_url, issuer=idp.issuer, audience=API, cooldown_duration=3600.0
        )
        verifier.verify(_tokens(idp)["access"])
        for number in range(200):
            token = idp.sign(
                {"iss": idp.issuer}, kid=f"unknown-{number}", key=idp.forged_key
            )
            with pytest.raises(TokenVerificationError):
                verifier.verify(token)
        assert idp.fetches(KEYS) == 1

    def test_a_rotated_key_is_accepted_after_the_cooldown(self, idp):
        verifier = IdTokenVerifier.from_jwks_url(
            idp.jwks_url, issuer=idp.issuer, client_id=CLIENT, cooldown_duration=0.0
        )
        verifier.verify(_tokens(idp)["id"], nonce=NONCE)
        idp.publish("k2")
        now = int(time.time())
        token = idp.sign(
            {
                "iss": idp.issuer,
                "aud": CLIENT,
                "sub": "u",
                "nonce": NONCE,
                "iat": now,
                "exp": now + 60,
            },
            kid="k2",
        )
        assert verifier.verify(token, nonce=NONCE)["sub"] == "u"
