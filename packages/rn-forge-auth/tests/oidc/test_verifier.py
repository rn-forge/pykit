"""Tests for the token verification half of rn_forge.auth.oidc. No real IdP."""

from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth.oidc import (  # noqa: E402
    JwtVerifier,
    TokenVerificationError,
    discover_oidc,
    fetch_json,
)

pytestmark = pytest.mark.unit

AUDIENCE = "api://orders"
KEYS = "/keys"
DISCOVERY = "/.well-known/openid-configuration"


def _verifier(idp, **kwargs):
    return JwtVerifier.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, audience=AUDIENCE, **kwargs
    )


class TestJwtVerifier:
    def test_valid_token_returns_claims(self, idp):
        claims = _verifier(idp).verify(idp.token(scp="orders.read"))
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
    def test_bad_claims_fail(self, idp, claims):
        verifier = _verifier(idp)
        token = idp.token(**claims)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_wrong_signature_fails(self, idp):
        verifier = _verifier(idp)
        token = idp.token(key=idp.forged_key)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_malformed_token_fails(self, idp):
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError):
            verifier.verify("not.a.jwt")

    def test_hmac_token_is_rejected_by_the_allow_list(self, idp):
        token = jwt.encode(
            {"sub": "u1"},
            "a-secret-of-at-least-thirty-two-bytes",
            algorithm="HS256",
            headers={"kid": "k1"},
        )
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError, match="not accepted"):
            verifier.verify(token)

    def test_unsigned_alg_none_token_is_rejected(self, idp):
        token = jwt.encode(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": AUDIENCE,
                "exp": int(time.time()) + 300,
            },
            None,
            algorithm="none",
            headers={"kid": "k1"},
        )
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError, match="not accepted"):
            verifier.verify(token)

    def test_token_without_kid_fails(self, idp):
        token = jwt.encode({"sub": "u1"}, idp.private_keys["k1"], algorithm="RS256")
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError, match="kid"):
            verifier.verify(token)

    def test_unknown_kid_fails(self, idp):
        token = idp.token(key=idp.forged_key, kid="nope")
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_unreachable_key_set_fails(self, idp):
        verifier = JwtVerifier.from_jwks_url(
            "http://127.0.0.1:1/keys", issuer=idp.issuer, audience=AUDIENCE
        )
        token = idp.token()
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    @pytest.mark.parametrize("url", ["http://idp.example.com/keys", "ftp://idp/keys"])
    def test_a_non_https_key_set_url_is_refused(self, url):
        with pytest.raises(TokenVerificationError, match="Refusing"):
            JwtVerifier.from_jwks_url(url, issuer="iss", audience=AUDIENCE)


class TestKeyCaching:
    def test_cache_hit_avoids_a_second_fetch(self, idp):
        verifier = _verifier(idp)
        verifier.verify(idp.token())
        verifier.verify(idp.token())
        assert idp.fetches(KEYS) == 1

    def test_rotated_key_is_picked_up_once_the_cooldown_allows(self, idp):
        verifier = _verifier(idp, cooldown_duration=0.0)
        verifier.verify(idp.token())
        idp.publish("k2")
        assert verifier.verify(idp.token(kid="k2"))["sub"] == "u1"
        assert idp.fetches(KEYS) == 2

    def test_rotated_key_is_refused_during_the_cooldown(self, idp):
        verifier = _verifier(idp, cooldown_duration=3600.0)
        verifier.verify(idp.token())
        idp.publish("k2")
        token = idp.token(kid="k2")
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)
        assert idp.fetches(KEYS) == 1

    def test_refetch_is_bounded_under_a_forged_kid_storm(self, idp):
        verifier = _verifier(idp, cooldown_duration=3600.0)
        verifier.verify(idp.token())
        forged = idp.token(key=idp.forged_key, kid="forged")
        for _ in range(10):
            with pytest.raises(TokenVerificationError):
                verifier.verify(forged)
        assert idp.fetches(KEYS) == 1

    def test_key_set_is_refetched_after_its_lifespan(self, idp, monkeypatch):
        verifier = _verifier(idp, lifespan=100.0)
        verifier.verify(idp.token())
        later = time.monotonic() + 101
        monkeypatch.setattr(jwt.jwk_set_cache.time, "monotonic", lambda: later)
        verifier.verify(idp.token())
        assert idp.fetches(KEYS) == 2


class TestDiscovery:
    def test_from_issuer_reads_the_well_known_document(self, idp):
        verifier = JwtVerifier.from_issuer(idp.issuer, audience=AUDIENCE)
        assert verifier.verify(idp.token())["sub"] == "u1"
        assert idp.requests[0].path.endswith(DISCOVERY)

    def test_issuer_mismatch_is_rejected(self):
        with pytest.raises(TokenVerificationError, match="does not match"):
            discover_oidc(
                "https://idp.example.com",
                fetch=lambda url: {"issuer": "https://other", "jwks_uri": "u"},
            )

    def test_incomplete_document_is_rejected(self):
        with pytest.raises(TokenVerificationError, match="incomplete"):
            discover_oidc("https://idp.example.com", fetch=lambda url: {"issuer": "x"})

    def test_a_discovered_non_https_jwks_uri_is_refused(self):
        issuer = "https://idp.example.com"
        document = {"issuer": issuer, "jwks_uri": "http://idp.example.com/keys"}
        with pytest.raises(TokenVerificationError, match="Refusing"):
            JwtVerifier.from_issuer(
                issuer, audience=AUDIENCE, fetch=lambda url: document
            )


class TestFetchJson:
    @pytest.mark.parametrize(
        "url", ["http://idp.example.com/keys", "ftp://idp/keys", "file:///etc/passwd"]
    )
    def test_refuses_insecure_schemes(self, url):
        with pytest.raises(TokenVerificationError, match="Refusing"):
            fetch_json(url)

    def test_reads_a_json_object_from_a_local_host(self, idp):
        assert fetch_json(idp.jwks_url)["keys"]

    def test_an_unreachable_host_is_a_verification_error(self):
        with pytest.raises(TokenVerificationError, match="Could not fetch"):
            fetch_json("http://127.0.0.1:1/keys")
