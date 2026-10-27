"""The logout-token profile: LogoutTokenVerifier."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth import InMemoryReplayStore  # noqa: E402
from rn_forge.auth.oidc import LogoutTokenVerifier, TokenVerificationError  # noqa: E402

pytestmark = pytest.mark.unit

CLIENT = "web-login"
EVENT = "http://schemas.openid.net/event/backchannel-logout"


def _verifier(idp, store=None, **kwargs):
    return LogoutTokenVerifier.from_jwks_url(
        idp.jwks_url,
        issuer=idp.issuer,
        client_id=CLIENT,
        replay_store=store or InMemoryReplayStore(),
        **kwargs,
    )


_JTI = iter(range(10_000))


def _claims(idp, **overrides):
    now = int(time.time())
    return {
        "iss": idp.issuer,
        "aud": CLIENT,
        "iat": now,
        "exp": now + 120,
        "jti": f"jti-{next(_JTI)}",
        "sid": "s1",
        "events": {EVENT: {}},
        **overrides,
    }


def _token(idp, typ="logout+jwt", **overrides):
    return idp.sign(_claims(idp, **overrides), typ=typ)


def test_a_valid_logout_token_returns_its_claims(idp):
    assert _verifier(idp).verify(_token(idp))["sid"] == "s1"


def test_a_sub_alone_is_enough(idp):
    assert _verifier(idp).verify(_token(idp, sid=None, sub="u1"))["sub"] == "u1"


@pytest.mark.parametrize(
    "typ", ["logout+jwt", "application/logout+jwt", "LOGOUT+JWT", None]
)
def test_a_logout_type_or_none_is_accepted(idp, typ):
    assert _verifier(idp).verify(_token(idp, typ=typ))


@pytest.mark.parametrize("typ", ["JWT", "at+jwt", "id_token"])
def test_any_other_typ_is_rejected(idp, typ):
    with pytest.raises(TokenVerificationError, match="typ"):
        _verifier(idp).verify(_token(idp, typ=typ))


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example.com"},
        {"aud": "someone-else"},
        {"exp": int(time.time()) - 60},
        {"iat": None},
        {"exp": None},
        {"jti": None},
        {"events": None},
        {"events": ["not", "an", "object"]},
        {"events": {"other-event": {}}},
        {"events": {EVENT: "not-an-object"}},
        {"sid": None},
        {"nonce": "n"},
        {"iat": int(time.time()) - 3600, "exp": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600, "exp": int(time.time()) + 7200},
    ],
    ids=[
        "iss",
        "aud",
        "expired",
        "no-iat",
        "no-exp",
        "no-jti",
        "no-events",
        "events-not-object",
        "wrong-event",
        "event-value-not-object",
        "neither-sid-nor-sub",
        "nonce",
        "iat-too-old",
        "iat-in-future",
    ],
)
def test_a_bad_logout_token_is_rejected(idp, overrides):
    with pytest.raises(TokenVerificationError):
        _verifier(idp).verify(_token(idp, **overrides))


def test_the_iat_window_is_configurable(idp):
    token = _token(idp, iat=int(time.time()) - 300, exp=int(time.time()) + 300)
    with pytest.raises(TokenVerificationError, match="issued more than"):
        _verifier(idp).verify(token)
    assert _verifier(idp, max_age_seconds=600).verify(token)


def test_a_replayed_jti_is_rejected(idp):
    verifier = _verifier(idp)
    token = _token(idp, jti="once")
    verifier.verify(token)
    with pytest.raises(TokenVerificationError, match="already used"):
        verifier.verify(token)


def test_the_jti_is_recorded_per_issuer_until_exp(idp):
    store = InMemoryReplayStore()
    _verifier(idp, store).verify(_token(idp, jti="j"))
    assert store.record_once(f"{idp.issuer}|j", ttl=timedelta(days=1)) is False


def test_a_rejected_token_does_not_consume_its_jti(idp):
    verifier = _verifier(idp)
    with pytest.raises(TokenVerificationError):
        verifier.verify(_token(idp, jti="j", nonce="n"))
    assert verifier.verify(_token(idp, jti="j"))


def test_a_forged_token_does_not_consume_its_jti(idp):
    verifier = _verifier(idp)
    with pytest.raises(TokenVerificationError):
        verifier.verify(idp.sign(_claims(idp, jti="j"), key=idp.forged_key))
    assert verifier.verify(_token(idp, jti="j"))


def test_the_algorithm_allow_list_rejects_hmac(idp):
    token = jwt.encode(
        _claims(idp),
        "a-secret-of-at-least-thirty-two-bytes",
        algorithm="HS256",
        headers={"kid": "k1"},
    )
    with pytest.raises(TokenVerificationError, match="not accepted"):
        _verifier(idp).verify(token)
