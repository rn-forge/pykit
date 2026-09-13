"""Tests for rn_forge.commons.integration.auth. No test calls a real IdP."""

from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from rn_forge.commons.integration.auth import (  # noqa: E402
    JwksCache,
    JwtVerifier,
    TokenVerificationError,
    discover_oidc,
    fetch_json,
)

ISSUER = "https://idp.example.com/tenant"
AUDIENCE = "api://orders"
JWKS_URL = f"{ISSUER}/keys"


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY = _keypair()
OTHER_KEY = _keypair()


def _jwk(private_key, kid):
    return {
        **RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True),
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def _token(private_key=KEY, kid="k1", **claims):
    payload = {
        "sub": "u1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        **claims,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


class FakeIdP:
    def __init__(self, *keys):
        self.keys = list(keys)
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": JWKS_URL}
        return {"keys": list(self.keys)}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _verifier(idp, clock=None, **kwargs):
    cache = JwksCache(JWKS_URL, fetch=idp, clock=clock or FakeClock(), **kwargs)
    return JwtVerifier(jwks=cache, issuer=ISSUER, audience=AUDIENCE)


class TestJwtVerifier:
    def test_valid_token_returns_claims(self):
        claims = _verifier(FakeIdP(_jwk(KEY, "k1"))).verify(_token(scp="orders.read"))
        assert claims["sub"] == "u1"
        assert claims["scp"] == "orders.read"

    @pytest.mark.parametrize(
        "claims",
        [
            {"exp": int(time.time()) - 60},
            {"aud": "api://someone-else"},
            {"iss": "https://evil.example.com"},
            {"exp": None},
        ],
        ids=["expired", "wrong-audience", "wrong-issuer", "missing-exp"],
    )
    def test_bad_claims_fail(self, claims):
        with pytest.raises(TokenVerificationError):
            _verifier(FakeIdP(_jwk(KEY, "k1"))).verify(_token(**claims))

    def test_wrong_signature_fails(self):
        with pytest.raises(TokenVerificationError):
            _verifier(FakeIdP(_jwk(KEY, "k1"))).verify(_token(private_key=OTHER_KEY))

    def test_malformed_token_fails(self):
        with pytest.raises(TokenVerificationError):
            _verifier(FakeIdP(_jwk(KEY, "k1"))).verify("not.a.jwt")

    def test_hmac_token_is_rejected_by_the_allow_list(self):
        token = jwt.encode(
            {"sub": "u1"}, "secret", algorithm="HS256", headers={"kid": "k1"}
        )
        with pytest.raises(TokenVerificationError, match="not accepted"):
            _verifier(FakeIdP(_jwk(KEY, "k1"))).verify(token)

    def test_token_without_kid_fails(self):
        token = jwt.encode({"sub": "u1"}, KEY, algorithm="RS256")
        with pytest.raises(TokenVerificationError, match="kid"):
            _verifier(FakeIdP(_jwk(KEY, "k1"))).verify(token)


class TestJwksCache:
    def test_cache_hit_avoids_a_second_fetch(self):
        idp = FakeIdP(_jwk(KEY, "k1"))
        verifier = _verifier(idp)
        verifier.verify(_token())
        verifier.verify(_token())
        assert len(idp.calls) == 1

    def test_unknown_kid_triggers_exactly_one_refetch_then_rotation_is_picked_up(self):
        idp, clock = FakeIdP(_jwk(KEY, "k1")), FakeClock()
        verifier = _verifier(idp, clock)
        verifier.verify(_token())
        clock.now += 60
        idp.keys.append(_jwk(OTHER_KEY, "k2"))
        assert verifier.verify(_token(private_key=OTHER_KEY, kid="k2"))["sub"] == "u1"
        assert len(idp.calls) == 2

    def test_refetch_is_bounded_under_a_forged_kid_storm(self):
        idp, clock = FakeIdP(_jwk(KEY, "k1")), FakeClock()
        verifier = _verifier(idp, clock)
        verifier.verify(_token())
        clock.now += 60
        for _ in range(10):
            with pytest.raises(TokenVerificationError):
                verifier.verify(_token(kid="forged"))
        assert len(idp.calls) == 2

    def test_max_age_expiry_refetches(self):
        idp, clock = FakeIdP(_jwk(KEY, "k1")), FakeClock()
        verifier = _verifier(idp, clock, max_age=100)
        verifier.verify(_token())
        clock.now += 101
        verifier.verify(_token())
        assert len(idp.calls) == 2

    def test_unusable_key_set_fails(self):
        with pytest.raises(TokenVerificationError):
            JwksCache(JWKS_URL, fetch=lambda url: {"keys": []}).get_signing_key("k1")


class TestDiscovery:
    def test_discovery_reads_the_well_known_document(self):
        idp = FakeIdP(_jwk(KEY, "k1"))
        verifier = JwtVerifier.from_issuer(ISSUER, audience=AUDIENCE, fetch=idp)
        assert verifier.verify(_token())["sub"] == "u1"
        assert idp.calls[0] == f"{ISSUER}/.well-known/openid-configuration"

    def test_issuer_mismatch_is_rejected(self):
        with pytest.raises(TokenVerificationError, match="does not match"):
            discover_oidc(
                ISSUER,
                fetch=lambda url: {"issuer": "https://other", "jwks_uri": JWKS_URL},
            )

    def test_incomplete_document_is_rejected(self):
        with pytest.raises(TokenVerificationError, match="incomplete"):
            discover_oidc(ISSUER, fetch=lambda url: {"issuer": ISSUER})


class TestFetchJson:
    @pytest.mark.parametrize(
        "url", ["http://idp.example.com/keys", "ftp://idp/keys", "file:///etc/passwd"]
    )
    def test_refuses_insecure_schemes(self, url):
        with pytest.raises(TokenVerificationError, match="Refusing"):
            fetch_json(url)
