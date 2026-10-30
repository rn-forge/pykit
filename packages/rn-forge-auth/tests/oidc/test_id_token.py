"""The ID-token profile: IdTokenVerifier."""

from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("authlib")

from rn_forge.auth.oidc import IdTokenVerifier, TokenVerificationError  # noqa: E402

pytestmark = pytest.mark.unit

CLIENT = "web-login"
NONCE = "n-0S6_WzA2Mj"


def _verifier(idp, **kwargs):
    return IdTokenVerifier.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, client_id=CLIENT, **kwargs
    )


def _claims(idp, **overrides):
    now = int(time.time())
    return {
        "iss": idp.issuer,
        "aud": CLIENT,
        "sub": "u1",
        "exp": now + 300,
        "iat": now,
        "nonce": NONCE,
        **overrides,
    }


def _verify(idp, verifier=None, *, nonce=NONCE, access_token=None, **overrides):
    token = idp.sign(_claims(idp, **overrides))
    return (verifier or _verifier(idp)).verify(
        token, nonce=nonce, access_token=access_token
    )


def test_a_valid_id_token_returns_its_claims(idp):
    assert _verify(idp)["sub"] == "u1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example.com"},
        {"aud": "someone-else"},
        {"exp": int(time.time()) - 60},
        {"exp": None},
        {"iat": None},
        {"sub": None},
        {"iat": int(time.time()) + 3600},
        {"nonce": "another"},
        {"nonce": None},
        {"aud": [CLIENT, "second"]},
        {"aud": [CLIENT, "second"], "azp": "second"},
    ],
    ids=[
        "iss",
        "aud",
        "expired",
        "no-exp",
        "no-iat",
        "no-sub",
        "iat-in-future",
        "nonce-mismatch",
        "nonce-missing",
        "multi-aud-without-azp",
        "wrong-azp",
    ],
)
def test_a_bad_claim_is_rejected(idp, overrides):
    with pytest.raises(TokenVerificationError):
        _verify(idp, **overrides)


def test_an_empty_expected_nonce_is_rejected(idp):
    with pytest.raises(TokenVerificationError, match="nonce"):
        _verify(idp, nonce="")


def test_a_multi_audience_token_with_our_azp_is_accepted(idp):
    assert _verify(idp, aud=[CLIENT, "second"], azp=CLIENT)["azp"] == CLIENT


def test_at_hash_must_match_the_access_token(idp):
    from authlib.oidc.core.util import create_half_hash

    digest = create_half_hash("access-1", "RS256").decode()
    assert _verify(idp, at_hash=digest, access_token="access-1")
    with pytest.raises(TokenVerificationError):
        _verify(idp, at_hash=digest, access_token="access-2")


def test_a_bad_signature_is_rejected(idp):
    token = idp.sign(_claims(idp), key=idp.forged_key)
    verifier = _verifier(idp)
    with pytest.raises(TokenVerificationError):
        verifier.verify(token, nonce=NONCE)


def test_the_algorithm_allow_list_rejects_hmac_and_none(idp):
    secret = "a-secret-of-at-least-thirty-two-bytes"
    hmac_token = jwt.encode(
        _claims(idp), secret, algorithm="HS256", headers={"kid": "k1"}
    )
    unsigned = jwt.encode(_claims(idp), None, algorithm="none", headers={"kid": "k1"})
    for token in (hmac_token, unsigned):
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError, match="not accepted"):
            verifier.verify(token, nonce=NONCE)


class TestMaxAge:
    def test_a_recent_auth_time_is_accepted(self, idp):
        verifier = _verifier(idp, max_age=300)
        assert _verify(idp, verifier, auth_time=int(time.time()) - 30)

    def test_an_old_auth_time_is_rejected(self, idp):
        verifier = _verifier(idp, max_age=300)
        auth_time = int(time.time()) - 3600
        with pytest.raises(TokenVerificationError, match="max_age"):
            _verify(idp, verifier, auth_time=auth_time)

    def test_a_missing_auth_time_is_rejected(self, idp):
        verifier = _verifier(idp, max_age=300)
        with pytest.raises(TokenVerificationError):
            _verify(idp, verifier)

    def test_a_future_auth_time_is_rejected(self, idp):
        verifier = _verifier(idp, max_age=300)
        auth_time = int(time.time()) + 3600
        with pytest.raises(TokenVerificationError, match="future"):
            _verify(idp, verifier, auth_time=auth_time)

    def test_auth_time_is_not_required_without_max_age(self, idp):
        assert _verify(idp)


def test_from_issuer_uses_discovery(idp):
    verifier = IdTokenVerifier.from_issuer(idp.issuer, client_id=CLIENT)
    assert verifier.verify(idp.sign(_claims(idp)), nonce=NONCE)["sub"] == "u1"
